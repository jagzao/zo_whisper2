from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from transcript_pipeline.knowledge.gemini_embeddings import build_curated_chunks, evaluate_pack_readiness
from transcript_pipeline.knowledge.zavi_curated_import import build_import_payload, publisher_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or publish owner-approved curated knowledge to Zavi.")
    parser.add_argument("--pack", type=Path, required=True, help="Curated Session Knowledge Pack JSON")
    parser.add_argument("--owner-content-uat", choices=["PASS"], required=True)
    parser.add_argument("--audit", type=Path, required=True, help="Local audit output (no knowledge text)")
    parser.add_argument("--payload", type=Path, help="Optional private curated embedding payload output")
    parser.add_argument("--publish", action="store_true", help="Send approved chunks to the configured Zavi API")
    args = parser.parse_args()

    source_bytes = args.pack.read_bytes()
    pack = json.loads(source_bytes)
    readiness = evaluate_pack_readiness(pack, owner_content_uat=args.owner_content_uat)
    chunks = build_curated_chunks(pack, owner_content_uat=args.owner_content_uat,
                                  second_brain_ready=readiness["SECOND_BRAIN_READY"])
    audit: dict[str, Any] = {
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        **readiness,
        "EMBEDDING_READY": "YES" if chunks.get("DOCUMENT_EMBEDDING_READY") else "NO",
        "intended_chunks": len(chunks["intended_chunk_ids"]),
        "eligible_chunks": len(chunks["eligible_chunks"]),
        "rejected_chunks": len(chunks["rejected_chunks"]),
        "accepted_exclusion_count": len(chunks.get("accepted_exclusions", {})),
        "raw_transcript_published": False,
        "raw_ocr_published": False,
        "raw_media_published": False,
        "GEMINI_LIVE_SMOKE": "NOT_RUN",
        "SECOND_BRAIN_INGESTION": "NOT_RUN",
    }
    if args.payload:
        args.payload.parent.mkdir(parents=True, exist_ok=True)
        args.payload.write_text(json.dumps(chunks["eligible_chunks"], ensure_ascii=False, indent=2),
                                encoding="utf-8")
        audit["payload_path"] = str(args.payload)
    if args.publish:
        payload = build_import_payload(package_id=pack.get("media_id") or audit["source_sha256"],
                                       readiness=readiness, chunk_report=chunks)
        publisher = publisher_from_env()
        if publisher is None:
            audit["SECOND_BRAIN_INGESTION"] = "BLOCKED_PUBLISHER_CONFIG"
        else:
            result = publisher.publish(payload)
            audit["GEMINI_LIVE_SMOKE"] = "PASS" if result.get("syntheticSmoke") == "PASS" else "BLOCKED_OR_FAILED"
            audit["SECOND_BRAIN_INGESTION"] = "PASS" if result.get("success") else "FAILED"
            audit["ingestion_result"] = {key: result.get(key) for key in
                ("success", "syntheticSmoke", "model", "dimensions", "instructionVersion", "intended", "excluded",
                 "embedded", "unchanged", "inserted", "updated", "retired", "failed", "failedReasons")}
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "source_sha256"}, ensure_ascii=False))
    if audit["SECOND_BRAIN_READY"] != "PASS" or audit["EMBEDDING_READY"] != "YES":
        return 2
    return 0 if not args.publish or audit["SECOND_BRAIN_INGESTION"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
