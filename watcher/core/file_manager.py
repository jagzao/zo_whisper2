import os
import magic
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
import threading
import time

logger = logging.getLogger(__name__)

class FileValidationError(Exception):
    """Raised when file validation fails"""
    pass

class FileManager:
    """Robust file management with validation, cleanup, and monitoring"""
    
    SUPPORTED_VIDEO_MIMES = {
        'video/mp4', 'video/x-msvideo', 'video/quicktime', 
        'video/x-matroska', 'video/webm'
    }
    
    SUPPORTED_AUDIO_MIMES = {
        'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4',
        'audio/aac', 'audio/flac', 'audio/ogg'
    }
    
    SUPPORTED_EXTENSIONS = {
        '.mp4', '.avi', '.mov', '.mkv', '.webm',  # Video
        '.mp3', '.wav', '.m4a', '.aac', '.flac'   # Audio
    }
    
    def __init__(self, max_size_mb: int = 500, cleanup_temp: bool = True):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.cleanup_temp = cleanup_temp
        self._temp_files: Dict[str, float] = {}  # file_path -> creation_time
        self._lock = threading.Lock()
        
        # Start cleanup thread if enabled
        if self.cleanup_temp:
            self._start_cleanup_thread()
    
    def validate_file(self, file_path: str) -> Dict[str, any]:
        """
        Comprehensive file validation
        Returns dict with validation results and file metadata
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileValidationError(f"File does not exist: {file_path}")
        
        # Check file size
        file_size = file_path.stat().st_size
        if file_size > self.max_size_bytes:
            raise FileValidationError(
                f"File too large: {file_size / 1024 / 1024:.1f}MB "
                f"(max: {self.max_size_bytes / 1024 / 1024}MB)"
            )
        
        if file_size == 0:
            raise FileValidationError("File is empty")
        
        # Check extension
        extension = file_path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise FileValidationError(
                f"Unsupported file extension: {extension}. "
                f"Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )
        
        # Check MIME type using python-magic
        try:
            mime_type = magic.from_file(str(file_path), mime=True)
        except Exception as e:
            logger.warning(f"Could not determine MIME type for {file_path}: {e}")
            mime_type = "unknown"
        
        # Validate MIME type
        supported_mimes = self.SUPPORTED_VIDEO_MIMES | self.SUPPORTED_AUDIO_MIMES
        if mime_type != "unknown" and mime_type not in supported_mimes:
            raise FileValidationError(
                f"Unsupported MIME type: {mime_type}. "
                f"File may be corrupted or not a valid media file."
            )
        
        # Calculate file hash for deduplication
        file_hash = self._calculate_file_hash(file_path)
        
        # Determine media type
        is_video = extension in {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        is_audio = extension in {'.mp3', '.wav', '.m4a', '.aac', '.flac'}
        
        return {
            'path': str(file_path),
            'name': file_path.name,
            'size_bytes': file_size,
            'size_mb': round(file_size / 1024 / 1024, 2),
            'extension': extension,
            'mime_type': mime_type,
            'hash': file_hash,
            'is_video': is_video,
            'is_audio': is_audio,
            'created_at': datetime.fromtimestamp(file_path.stat().st_ctime),
            'modified_at': datetime.fromtimestamp(file_path.stat().st_mtime)
        }
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return "unknown"
    
    def register_temp_file(self, file_path: str) -> None:
        """Register a temporary file for cleanup"""
        with self._lock:
            self._temp_files[file_path] = time.time()
        logger.debug(f"Registered temp file: {file_path}")
    
    def cleanup_temp_file(self, file_path: str, force: bool = False) -> bool:
        """Clean up a specific temporary file"""
        try:
            file_path_obj = Path(file_path)
            if file_path_obj.exists() and (force or file_path in self._temp_files):
                file_path_obj.unlink()
                with self._lock:
                    self._temp_files.pop(file_path, None)
                logger.info(f"Cleaned up temp file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error cleaning up temp file {file_path}: {e}")
            return False
    
    def _start_cleanup_thread(self) -> None:
        """Start background thread for automatic cleanup of old temp files"""
        def cleanup_worker():
            while True:
                try:
                    current_time = time.time()
                    cleanup_list = []
                    
                    with self._lock:
                        for file_path, creation_time in list(self._temp_files.items()):
                            # Clean files older than 1 hour
                            if current_time - creation_time > 3600:
                                cleanup_list.append(file_path)
                    
                    for file_path in cleanup_list:
                        self.cleanup_temp_file(file_path, force=True)
                    
                    # Sleep for 10 minutes before next cleanup cycle
                    time.sleep(600)
                    
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
                    time.sleep(60)  # Sleep 1 minute on error
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.name = "FileCleanupThread"
        cleanup_thread.start()
        logger.info("Started file cleanup thread")
    
    def get_file_stats(self, directory: str) -> Dict[str, any]:
        """Get statistics about files in a directory"""
        directory = Path(directory)
        if not directory.exists():
            return {'error': f'Directory does not exist: {directory}'}
        
        stats = {
            'total_files': 0,
            'total_size_mb': 0,
            'video_files': 0,
            'audio_files': 0,
            'supported_files': 0,
            'unsupported_files': 0,
            'file_types': {},
            'largest_file': None,
            'oldest_file': None,
            'newest_file': None
        }
        
        oldest_time = None
        newest_time = None
        largest_size = 0
        
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                stats['total_files'] += 1
                file_size = file_path.stat().st_size
                stats['total_size_mb'] += file_size / 1024 / 1024
                
                extension = file_path.suffix.lower()
                stats['file_types'][extension] = stats['file_types'].get(extension, 0) + 1
                
                if extension in self.SUPPORTED_EXTENSIONS:
                    stats['supported_files'] += 1
                    if extension in {'.mp4', '.avi', '.mov', '.mkv', '.webm'}:
                        stats['video_files'] += 1
                    else:
                        stats['audio_files'] += 1
                else:
                    stats['unsupported_files'] += 1
                
                # Track largest file
                if file_size > largest_size:
                    largest_size = file_size
                    stats['largest_file'] = {
                        'path': str(file_path),
                        'size_mb': round(file_size / 1024 / 1024, 2)
                    }
                
                # Track oldest and newest files
                mod_time = file_path.stat().st_mtime
                if oldest_time is None or mod_time < oldest_time:
                    oldest_time = mod_time
                    stats['oldest_file'] = {
                        'path': str(file_path),
                        'modified': datetime.fromtimestamp(mod_time).isoformat()
                    }
                
                if newest_time is None or mod_time > newest_time:
                    newest_time = mod_time
                    stats['newest_file'] = {
                        'path': str(file_path),
                        'modified': datetime.fromtimestamp(mod_time).isoformat()
                    }
        
        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        return stats
    
    def check_disk_space(self, path: str, required_mb: int = 1000) -> Dict[str, any]:
        """Check available disk space"""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                path_obj = path_obj.parent
            
            stat = os.statvfs(str(path_obj)) if hasattr(os, 'statvfs') else None
            if stat:
                # Unix/Linux
                free_bytes = stat.f_bavail * stat.f_frsize
                total_bytes = stat.f_blocks * stat.f_frsize
            else:
                # Windows
                import shutil
                total_bytes, used_bytes, free_bytes = shutil.disk_usage(str(path_obj))
            
            free_mb = free_bytes / 1024 / 1024
            total_mb = total_bytes / 1024 / 1024
            used_mb = total_mb - free_mb
            
            return {
                'free_mb': round(free_mb, 2),
                'total_mb': round(total_mb, 2),
                'used_mb': round(used_mb, 2),
                'free_percent': round((free_mb / total_mb) * 100, 2),
                'sufficient_space': free_mb > required_mb,
                'required_mb': required_mb
            }
            
        except Exception as e:
            logger.error(f"Error checking disk space for {path}: {e}")
            return {'error': str(e)}

# Global file manager instance
file_manager = FileManager()