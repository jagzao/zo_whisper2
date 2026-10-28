"""Production orchestration for resumable Documents V3 generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.session_pack import (
    generate_cross_session_knowledge,
    generate_session_pack,
    normalize_evidence_bundle,
)

PIPELINE_VERSION = "3"
EVIDENCE_VERSION = "1"
PILOT_GATES = (
    "CLAIM_PROVENANCE", "APPLICATION_ISOLATION", "VISUAL_COVERAGE",
    "PROCEDURE_GROUNDING", "DIAGRAM_GROUNDING", "TIMELINE_ORDER", "SOURCE_DEDUP", "QUALITY",
)
CORPUS_GATES = (
    "SESSION_41_OWNER_UAT", "GOLDEN_2_OWNER_UAT", "GOLDEN_OVERFIT_CHECK",
    "REAL_CROSS_SESSION_GATE", "PILOT_GATE",
)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def evaluate_corpus_gate(gates: dict[str, str]) -> dict[str, Any]:
    missing = [name for name in CORPUS_GATES if gates.get(name) != "PASS"]
    return {"status": "PASS" if not missing else "FROZEN", "corpus_generation": "READY" if not missing else "FROZEN",
            "missing_or_failed": missing}


def build_media_evidence_bundle(*, media_id: str, video_metadata: dict[str, Any],
                                transcript_segments: list[dict[str, Any]], speech_coverage: dict[str, Any],
                                visual_report: dict[str, Any], evidence_events: list[dict[str, Any]]) -> dict[str, Any]:
    frames = []
    topics: dict[str, dict[str, Any]] = {}
    for source in visual_report.get("frames", []):
        frame = {key: source.get(key) for key in (
            "frame_id", "timestamp", "ocr_status", "ocr_text", "ocr_confidence", "retry_count", "engine",
            "source_image", "visual_type", "semantic_topic", "selected", "nodes", "edges", "provenance",
            "transcript_text", "application",
        ) if key in source}
        frames.append(frame)
        topic = source.get("semantic_topic")
        if topic:
            entry = topics.setdefault(str(topic), {"topic": str(topic), "frame_ids": []})
            entry["frame_ids"].append(str(source.get("frame_id", "")))
    return {
        "media_id": media_id,
        "video_metadata": dict(video_metadata),
        "transcript_segments": [dict(item) for item in transcript_segments],
        "speech_coverage": dict(speech_coverage),
        "frames": frames,
        "ocr_results": [{key: frame.get(key) for key in ("frame_id", "ocr_status", "ocr_text", "ocr_confidence", "retry_count", "engine", "source_image")}
                        for frame in frames],
        "visual_topics": list(topics.values()),
        "application_candidates": [],
        "evidence_events": [dict(item) for item in evidence_events],
    }


def document_state(evidence_path: Path, pack_path: Path | None = None) -> dict[str, Any]:
    reason = None
    quality_state = None
    quality_gates: dict[str, Any] = {}
    if not evidence_path.is_file():
        state = "BLOCKED_SOURCE"
        reason = "Normalized source evidence is not available."
    else:
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            media_id = str(evidence.get("media_id", ""))
            speech = evidence.get("speech_coverage", {})
            transcript = speech.get("transcript_state")
            manifest_path = evidence_path.parent.parent / "v3" / "generation-state.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            generation = manifest.get("sources", {}).get(media_id, {}).get("GENERATION_STATE")
            if generation in {"GENERATING", "PENDING"}:
                state = "GENERATING"
            elif generation in {"FAILED", "FAILED_RECOVERABLE"}:
                state = "BLOCKED_SOURCE"
                reason = "Previous generation failed; persisted diagnostics are available for recovery."
            elif transcript == "MISSING":
                state = "TRANSCRIPT_MISSING"
                reason = "A source transcript is missing."
            elif transcript == "PARTIAL":
                state = "TRANSCRIPT_PARTIAL"
                reason = "Transcript coverage is partial."
            elif transcript == "NEEDS_REVIEW" or speech.get("speech_quality_gate") != "PASS":
                state = "TRANSCRIPT_NEEDS_REVIEW"
                reason = "Speech coverage has not passed its review gate."
            elif not pack_path or not pack_path.is_file():
                state = "READY_FOR_V3"
            else:
                pack = json.loads(pack_path.read_text(encoding="utf-8"))
                quality_state = pack.get("quality_state")
                quality_gates = pack.get("quality_gates", {})
                state = "V3_READY" if pack.get("quality_state") == "READY" and all(
                    Path(str(pack_path.parent / f"{Path(pack.get('source_video', evidence_path.stem)).stem}{ext}")).is_file()
                    for ext in (".md", ".pdf", ".json")
                ) else "V3_NEEDS_REVIEW"
                if state == "V3_NEEDS_REVIEW":
                    reason = "Pack quality gates or generated output files are incomplete."
        except (OSError, ValueError, TypeError):
            state = "BLOCKED_SOURCE"
    return {"documentation_state": state, "evidence_state": "AVAILABLE" if evidence_path.is_file() else "MISSING",
            "quality_state": quality_state, "quality_gates": quality_gates, "reason": reason,
            "evidence_path": str(evidence_path), "pack_path": str(pack_path) if pack_path else None}


def run_session_pack(bundle: Any, output_dir: Path) -> dict[str, Any]:
    evidence = normalize_evidence_bundle(bundle)
    source_id = evidence.media_id
    source_hash = _digest(evidence.__dict__)
    manifest_path = output_dir / "generation-state.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {"schema_version": 1, "sources": {}}
    record = manifest["sources"].get(source_id, {})
    if record.get("SOURCE_HASH") == source_hash and record.get("PIPELINE_VERSION") == PIPELINE_VERSION:
        outputs = {Path(path): digest for path, digest in record.get("OUTPUT_HASHES", {}).items()}
        if outputs and all(path.is_file() and _digest(path.read_bytes().hex()) == digest
                           for path, digest in outputs.items()):
            return {"status": record["QUALITY_STATE"], "state": "RESUMED", "paths": list(outputs),
                    "generation_state": record["GENERATION_STATE"]}
    record = {"SOURCE_ID": source_id, "SOURCE_HASH": source_hash,
              "INPUT_EVIDENCE_VERSION": EVIDENCE_VERSION, "PIPELINE_VERSION": PIPELINE_VERSION,
              "OUTPUT_HASHES": {}, "QUALITY_STATE": "GENERATING", "GENERATION_STATE": "GENERATING"}
    manifest["sources"][source_id] = record
    _atomic_json(manifest_path, manifest)
    try:
        result = generate_session_pack(evidence, output_dir)
        paths = result.get("paths") or ({"diagnostic": result["diagnostic"]} if result.get("diagnostic") else {})
        output_hashes = {str(Path(path)): _digest(Path(path).read_bytes().hex()) for path in paths.values() if Path(path).is_file()}
        status = "READY" if result["status"] == "READY" else "NEEDS_REVIEW"
        record.update(OUTPUT_HASHES=output_hashes, QUALITY_STATE=status,
                      GENERATION_STATE="READY" if status == "READY" else "NEEDS_REVIEW")
        manifest["sources"][source_id] = record
        _atomic_json(manifest_path, manifest)
        return {**result, "generation_state": record["GENERATION_STATE"]}
    except Exception:
        record["QUALITY_STATE"] = "FAILED_RECOVERABLE"
        record["GENERATION_STATE"] = "FAILED_RECOVERABLE"
        _atomic_json(manifest_path, manifest)
        raise


def run_golden2(bundle: Any, output_dir: Path) -> dict[str, Any]:
    evidence = normalize_evidence_bundle(bundle)
    if evidence.video_metadata.get("media_valid") is False or evidence.video_metadata.get("eligible") is False:
        output_dir.mkdir(parents=True, exist_ok=True)
        diagnostic = output_dir / f"{Path(str(evidence.video_metadata.get('basename') or evidence.media_id)).stem}-diagnostic.json"
        _atomic_json(diagnostic, {"media_id": evidence.media_id, "quality_state": "BLOCKED_SOURCE",
                                  "reason": "Source eligibility gate failed."})
        return {"status": "BLOCKED_SOURCE", "golden2_state": "NEEDS_REVIEW",
                "diagnostic": diagnostic, "diagnostics_persisted": True}
    result = run_session_pack(bundle, output_dir)
    if result["status"] != "READY":
        return {**result, "golden2_state": "NEEDS_REVIEW", "diagnostics_persisted": True}
    return {**result, "golden2_state": "TECHNICAL_PASS_OWNER_REVIEW_PENDING"}


def _pilot_gate_map(pack: dict[str, Any]) -> dict[str, str]:
    gates = pack.get("quality_gates", {})
    return {
        "CLAIM_PROVENANCE": gates.get("CLAIM_LEDGER", "FAIL"),
        "APPLICATION_ISOLATION": gates.get("APPLICATION_CLAIM_ISOLATION", "FAIL"),
        "VISUAL_COVERAGE": gates.get("VISUAL_TOPIC_COVERAGE", "FAIL"),
        "PROCEDURE_GROUNDING": gates.get("PROCEDURE_GROUNDING", "FAIL"),
        "DIAGRAM_GROUNDING": gates.get("DIAGRAM_PROVENANCE", "FAIL"),
        "TIMELINE_ORDER": gates.get("EVIDENCE_TIMELINE_CHRONOLOGICAL", "FAIL"),
        "SOURCE_DEDUP": gates.get("SOURCE_ARTIFACT_DEDUP", "FAIL"),
        "QUALITY": "PASS" if pack.get("quality_state") == "READY" and gates.get("QUALITY_GATE") == "PASS" else "FAIL",
    }


def run_pilot(bundles: list[Any], output_dir: Path, limit: int = 3) -> dict[str, Any]:
    normalized = [asdict(normalize_evidence_bundle(bundle)) for bundle in bundles]
    normalized = [item for item in normalized if item.get("media_id")
                  and item.get("video_metadata", {}).get("media_valid") is not False
                  and item.get("video_metadata", {}).get("eligible") is not False]
    selected = sorted(normalized, key=lambda item: str(item.get("media_id", "")))[:max(0, limit)]
    items = []
    for bundle in selected:
        result = run_session_pack(bundle, output_dir / str(bundle.get("media_id", "unknown")))
        pack = result.get("pack", {})
        items.append({"media_id": bundle.get("media_id"), "status": result["status"], "gates": _pilot_gate_map(pack)})
    aggregate = {gate: "PASS" if items and all(item["gates"][gate] == "PASS" for item in items) else "FAIL"
                 for gate in PILOT_GATES}
    return {"status": "PASS" if items and all(value == "PASS" for value in aggregate.values()) else "FAIL",
            "selected": [item["media_id"] for item in items], "items": items, "gates": aggregate,
            "prevents_corpus_generation": any(value != "PASS" for value in aggregate.values())}


def discover_application_groups(session_packs: list[dict[str, Any]],
                                known_applications: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    alias_index: dict[str, set[str]] = {}
    for app in known_applications or []:
        app_id = str(app.get("application_id") or "").strip()
        if not app_id:
            continue
        for alias in [app.get("name"), *app.get("aliases", [])]:
            if alias:
                alias_index.setdefault(str(alias).casefold().strip(), set()).add(app_id)
    for pack in session_packs:
        session_id = str(pack.get("media_id") or "")
        for candidate in pack.get("application_candidates", []):
            signals = [str(candidate.get(key, "")).casefold().strip()
                       for key in ("application_id", "name", "visible_title", "cmdb_id", "domain") if candidate.get(key)]
            signals.extend(str(value).casefold().strip() for value in
                           [*candidate.get("aliases", []), *candidate.get("known_identifiers", []),
                            *candidate.get("identity_signals", [])] if value)
            ids = {app_id for signal in signals for app_id in alias_index.get(signal, set())}
            if candidate.get("application_id"):
                ids.add(str(candidate["application_id"]))
            explicit = bool(candidate.get("cmdb_id") or candidate.get("status") in {"MATCH_CONFIRMED", "CONFIRMED"})
            key = next(iter(ids)) if len(ids) == 1 else "ambiguous:" + (signals[0] if signals else session_id)
            state = "AMBIGUOUS" if len(ids) > 1 or candidate.get("status") == "AMBIGUOUS" else (
                "CONFIRMED" if explicit else "PROBABLE" if signals else "DISTINCT")
            group = groups.setdefault(key, {"application_id": None if state == "AMBIGUOUS" else key,
                                             "candidate_state": state, "sessions": [], "candidates": []})
            if session_id and session_id not in group["sessions"]:
                group["sessions"].append(session_id)
            group["candidates"].append(candidate)
    return list(groups.values())


def generate_cross_session_from_directory(session_pack_dir: Path, output_dir: Path,
                                          known_applications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    packs = []
    for path in sorted(session_pack_dir.glob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if pack.get("document_type") == "SESSION_KNOWLEDGE_PACK" and pack.get("quality_state") == "READY":
            packs.append(pack)
    sessions = {pack.get("source_identity") or pack.get("media_id") for pack in packs}
    if len(sessions) < 2:
        return {"status": "BLOCKED_NO_ELIGIBLE_PAIR", "mission_packs": [], "eligible_session_count": len(sessions)}
    result = generate_cross_session_knowledge(packs, output_dir, known_applications=known_applications)
    return {**result, "status": result["status"] if result["mission_packs"] else "BLOCKED_NO_ELIGIBLE_PAIR",
            "eligible_session_count": len(sessions)}


def generate_full_corpus(session_pack_dir: Path, output_dir: Path, gates: dict[str, str],
                         known_applications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    eligibility = evaluate_corpus_gate(gates)
    if eligibility["status"] != "PASS":
        return {**eligibility, "mission_packs": [], "status": "FROZEN"}
    result = generate_cross_session_from_directory(session_pack_dir, output_dir, known_applications)
    return {**result, "corpus_generation": "READY" if result["status"] == "READY" else "FROZEN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Documents V3 application knowledge after authoritative runtime gates pass.")
    parser.add_argument("--session-packs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True, help="JSON map of authoritative corpus gate states")
    parser.add_argument("--applications", type=Path, help="Optional JSON application identity catalog")
    args = parser.parse_args(argv)
    gates = json.loads(args.gates.read_text(encoding="utf-8"))
    applications = json.loads(args.applications.read_text(encoding="utf-8")) if args.applications else None
    result = generate_full_corpus(args.session_packs, args.output, gates, applications)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
