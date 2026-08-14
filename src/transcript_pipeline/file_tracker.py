"""FileTracker — content-hash idempotency.

Avoids reprocessing an already-transcribed file. Two hash modes,
controlled by `FILE_TRACKER_HASH_MODE` (default "fast"):

- "fast": size + mtime + MD5 of the first 8KB. Cheap even for large
  videos — doesn't read the whole file. This is an idempotency
  fingerprint, not a cryptographic integrity guarantee: two different
  files that happen to share size, mtime, and their first 8KB would
  collide (unlikely in practice, not impossible), and a tool that
  rewrites a file in place without bumping mtime would go undetected.
- "full": SHA-256 of the entire file's content, streamed in chunks.
  Correctly detects any content change regardless of mtime/size
  quirks, at the cost of reading the whole file — meaningfully slower
  for large videos, so it's opt-in, not the default.

Falls back to detecting an existing transcription in
CarpetaTranscripciones/ either way.

`is_file_processed()`'s path-keyed lookup (`processed_files[<absolute
path>]`) revalidates the stored `hash` field against a freshly computed
one before trusting it — otherwise a file whose content changed at the
same path would still read as "already processed" from the old record,
which defeated "full" mode's whole purpose. Legacy records written before
the `hash` field existed (no `hash` key at all) are trusted on path match
alone — a deliberately conservative compatibility policy for old
`processed_files.json` databases, not a security boundary.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from transcript_pipeline.config import AUDIO_DIR, PROCESSED_FILES_DB, TRANSCRIPTIONS_DIR, VIDEOS_DIR
from transcript_pipeline.settings import SETTINGS

logger = logging.getLogger(__name__)

_FULL_HASH_CHUNK_SIZE = 1024 * 1024  # 1MB


class FileTracker:
    """Tracker of processed files, persisted to a local JSON file."""

    def __init__(self, db_path: Path = PROCESSED_FILES_DB, hash_mode: str | None = None):
        self.db_path = Path(db_path)
        self.hash_mode = hash_mode or SETTINGS.file_tracker_hash_mode
        self.processed_files = self.load_database()

    def load_database(self) -> dict:
        if self.db_path.exists():
            try:
                with open(self.db_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Error loading DB: %s", e)
                return {}
        return {}

    def save_database(self) -> None:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.processed_files, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Error saving DB: %s", e)

    def get_file_hash(self, file_path: Path) -> str:
        """Fingerprint used for idempotency — see module docstring for what
        "fast" vs "full" (`self.hash_mode`) each actually guarantee."""
        try:
            if self.hash_mode == "full":
                return self._full_file_hash(file_path)

            stat = file_path.stat()
            size = stat.st_size
            mtime = int(stat.st_mtime)

            with open(file_path, "rb") as f:
                chunk = f.read(8192)

            content = f"{size}_{mtime}_{hashlib.md5(chunk).hexdigest()}"
            return hashlib.sha256(content.encode()).hexdigest()[:16]

        except Exception as e:
            logger.warning("Error computing hash for %s: %s", file_path, e)
            return hashlib.md5(f"{file_path}_{file_path.stat().st_size}".encode()).hexdigest()[:16]

    @staticmethod
    def _full_file_hash(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(_FULL_HASH_CHUNK_SIZE), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def is_file_processed(self, file_path: Path) -> bool:
        try:
            file_hash = self.get_file_hash(file_path)
            file_key = str(file_path.absolute())

            if file_hash in self.processed_files:
                info = self.processed_files[file_hash]
                logger.debug("[HASH] Already processed: %s (%s)", file_path.name, info.get("date", "unknown"))
                return True

            if file_key in self.processed_files:
                info = self.processed_files[file_key]
                stored_hash = info.get("hash")
                if stored_hash is None:
                    # Legacy record predating the "hash" field — trust the
                    # path match (compat with old processed_files.json).
                    logger.debug("[PATH] Legacy record (no hash), trusting path match: %s", file_path.name)
                    return True
                if stored_hash == file_hash:
                    logger.debug("[PATH] Already processed: %s", file_path.name)
                    return True
                logger.debug("[PATH] Path matches but content hash diverged, reprocessing: %s", file_path.name)
                return False

            if self.transcription_exists(file_path):
                self.mark_as_processed(file_path, "auto_detected")
                return True

            return False

        except Exception as e:
            logger.error("Error checking file %s: %s", file_path, e)
            return False

    @staticmethod
    def _resolve_output_folder(file_path: Path) -> Path:
        """Mirrors SimpleScanProcessor.save_transcription()'s output-folder
        resolution — transcripts live under TRANSCRIPTIONS_DIR at the same
        relative path the source file has under AUDIO_DIR/VIDEOS_DIR."""
        for base in (AUDIO_DIR, VIDEOS_DIR):
            try:
                relative = file_path.resolve().relative_to(base.resolve())
                return TRANSCRIPTIONS_DIR / relative.parent
            except ValueError:
                continue
        return TRANSCRIPTIONS_DIR

    def transcription_exists(self, file_path: Path) -> bool:
        try:
            output_folder = self._resolve_output_folder(file_path)
            base_name = file_path.stem

            # Current format: no date prefix (matches save_transcription()).
            current_file = output_folder / f"{base_name}.txt"
            if current_file.exists() and current_file.stat().st_size > 100:
                return True

            # Legacy fallback: dated prefix, in case old transcripts (from
            # before this naming was simplified) are still on disk.
            for days_ago in range(0, 8):
                old_date = datetime.now() - timedelta(days=days_ago)
                old_prefix = old_date.strftime("%y_%m_%d")
                old_file = output_folder / f"{old_prefix}_{base_name}.txt"
                if old_file.exists() and old_file.stat().st_size > 100:
                    return True

            return False

        except Exception as e:
            logger.error("Error checking transcription for %s: %s", file_path, e)
            return False

    def mark_as_processed(self, file_path: Path, status: str = "success") -> None:
        try:
            file_hash = self.get_file_hash(file_path)
            file_key = str(file_path.absolute())

            info = {
                "path": file_key,
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "date": datetime.now().isoformat(),
                "status": status,
                "hash": file_hash,
            }

            self.processed_files[file_hash] = info
            self.processed_files[file_key] = info

            self.save_database()
            logger.info("[TRACKED] %s", file_path.name)

        except Exception as e:
            logger.error("Error marking file as processed %s: %s", file_path, e)

    def get_statistics(self) -> dict:
        try:
            hash_entries = {k: v for k, v in self.processed_files.items() if len(k) == 16 and k.isalnum()}

            total_files = len(hash_entries)
            total_size = sum(entry.get("size", 0) for entry in hash_entries.values())

            status_count: dict = {}
            for entry in hash_entries.values():
                status = entry.get("status", "unknown")
                status_count[status] = status_count.get(status, 0) + 1

            daily_count: dict = {}
            for entry in hash_entries.values():
                try:
                    date_str = entry.get("date", "").split("T")[0]
                    daily_count[date_str] = daily_count.get(date_str, 0) + 1
                except Exception:
                    pass

            return {
                "total_files": total_files,
                "total_size_gb": total_size / (1024**3),
                "status_breakdown": status_count,
                "daily_breakdown": dict(sorted(daily_count.items(), reverse=True)[:7]),
            }

        except Exception as e:
            logger.error("Error computing statistics: %s", e)
            return {"total_files": 0, "error": str(e)}

    def cleanup_old_entries(self, days: int = 30) -> None:
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            entries_to_remove = []

            for key, entry in self.processed_files.items():
                try:
                    if "path" in entry:
                        file_path = Path(entry["path"])
                        if not file_path.exists():
                            entry_date = datetime.fromisoformat(entry.get("date", "1970-01-01"))
                            if entry_date < cutoff_date:
                                entries_to_remove.append(key)
                except Exception:
                    entries_to_remove.append(key)

            for key in entries_to_remove:
                del self.processed_files[key]

            if entries_to_remove:
                self.save_database()
                logger.info("[CLEANUP] Removed %d old entries", len(entries_to_remove))

        except Exception as e:
            logger.error("Error during cleanup: %s", e)

    def scan_and_mark_existing(self, directories: list[str]) -> int:
        marked_count = 0
        supported_extensions = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".flac"}

        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                continue

            logger.info("[SCAN] Scanning: %s", dir_path)

            for file_path in dir_path.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                    if not self.is_file_processed(file_path) and self.transcription_exists(file_path):
                        self.mark_as_processed(file_path, "existing_transcription")
                        marked_count += 1

        logger.info("[SCAN] Marked %d files with existing transcriptions", marked_count)
        return marked_count
