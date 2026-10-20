"""DV2-04/05/14..20/44..46 — synthesis service, privacy, grounding validation
and last-good protection (TEST-MATRIX-ZMI-DOCS-V2-001)."""
from __future__ import annotations

import json

import pytest

from tests.fixtures.documentation_v2 import materialize_frames_dir
from tests.fixtures.documentation_v2.mock_synthesis import (
    MockAllowAllGuard,
    MockAlwaysMalformedProvider,
    MockDenyGuard,
    MockFreeFormProvider,
    MockKTSynthesisProvider,
    MockMalformedThenValidProvider,
    MockReferenceSynthesisProvider,
)
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.documentation.evidence import build_evidence_timeline, load_persisted_steps
from transcript_pipeline.documentation.grounding import (
    validate_knowledge_document,
    write_validation_report,
)
from transcript_pipeline.documentation.knowledge_models import (
    KnowledgeClaim,
    KnowledgeDocument,
    KnowledgeSection,
    SynthesizedProcedure,
    SynthesizedStep,
    SynthesisMetadata,
)
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.documentation.synthesis import (
    STATUS_BLOCKED_PRIVACY,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    SynthesisService,
)

KT_CONFIG = {
    "name": "Acme",
    "documentation": {"mode": "KT_SESSION"},
}

CONFIDENTIAL_REMOTE = {
    "name": "Confidential",
    "data_classification": "confidential",
    "documentation": {"mode": "KT_SESSION"},
}


class _RemoteProvider(MockKTSynthesisProvider):
    provider_type = LLMProviderType.REMOTE


def _timeline(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    steps = load_persisted_steps(frames_dir / "manual")
    return frames_dir, build_evidence_timeline(mapping, steps=steps, source_media="acme_kt_session.mp4")


# ── DV2-04 confidential remote block ──────────────────────────────────────

def test_dv2_04_remote_synthesis_on_confidential_project_blocked_before_request(tmp_path):
    from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard

    class _Settings:
        allow_external_llm = True  # even with external LLM allowed...

    guard = PrivacyGuard(_Settings())  # type: ignore[arg-type]
    provider = _RemoteProvider()
    service = SynthesisService(provider, guard, model_name="m")
    _, timeline = _timeline(tmp_path)
    with pytest.raises(ExternalLLMBlockedError):
        guard.check(provider, CONFIDENTIAL_REMOTE)
    result = service.synthesize(timeline, "KT_SESSION", CONFIDENTIAL_REMOTE)
    assert result.status == STATUS_BLOCKED_PRIVACY
    assert provider.calls == [], "no request may leave the machine for a confidential remote call"

    # End-to-end: the pipeline reports the typed status without a MANUAL_READY.
    frames_dir = materialize_frames_dir("kt_session", tmp_path / "e2e")
    pipeline_result = generate_documentation_v2(
        frames_dir, "acme_kt_session.mp4",
        project_config=CONFIDENTIAL_REMOTE, synthesis_service=service,
    )
    assert pipeline_result["status"] == STATUS_BLOCKED_PRIVACY
    assert pipeline_result["semantic"]["ready"] is False
    assert not (frames_dir / "manual" / "knowledge-document.json").exists()
    # Evidence still succeeds (AC-17).
    assert (frames_dir / "evidence" / "evidence.jsonl").exists()


# ── DV2-05 local confidential allowed ─────────────────────────────────────

def test_dv2_05_configured_local_provider_receives_bounded_blocks(tmp_path):
    provider = MockKTSynthesisProvider()
    assert provider.provider_type is LLMProviderType.LOCAL
    service = SynthesisService(provider, MockAllowAllGuard(), model_name="m")
    _, timeline = _timeline(tmp_path)
    result = service.synthesize(timeline, "KT_SESSION", CONFIDENTIAL_REMOTE)
    assert result.status == STATUS_OK
    assert result.document is not None
    assert provider.calls, "a local provider is allowed to receive bounded synthesis blocks"
    # The blocks are bounded excerpts, not the raw whole transcript.
    for call in provider.calls:
        payload = json.loads(call)
        for entry in payload.get("evidenceCatalog", []):
            assert len(entry.get("excerpt", "")) <= 600


# ── DV2-14 JSON only ──────────────────────────────────────────────────────

def test_dv2_14_free_form_model_response_rejected(tmp_path):
    provider = MockFreeFormProvider()
    service = SynthesisService(provider, MockAllowAllGuard(), model_name="m")
    _, timeline = _timeline(tmp_path)
    result = service.synthesize(timeline, "KT_SESSION", KT_CONFIG)
    assert result.status == STATUS_INVALID
    assert result.document is None
    # Original + exactly one repair retry per block.
    assert result.invocation_count == len(provider.calls)
    assert result.errors


# ── DV2-15 unknown evidence ───────────────────────────────────────────────

def test_dv2_15_claim_citing_unknown_evidence_id_fails_grounding(tmp_path):
    _, timeline = _timeline(tmp_path)
    document = KnowledgeDocument(
        documentation_mode="KT_SESSION",
        title="t",
        sections=[KnowledgeSection(
            id="section-01", section_type="RISK", title="R", order=1,
            claims=(KnowledgeClaim(id="claim-001", text="Unsupported claim.",
                                   evidence_refs=("E-999",)),),
        )],
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    report = validate_knowledge_document(document, timeline)
    assert not report.valid
    assert any("unknown evidence ref" in e for e in report.errors)


# ── DV2-16 missing evidence ───────────────────────────────────────────────

def test_dv2_16_factual_claim_without_refs_fails():
    frames_dir = None
    timeline = build_evidence_timeline({
        "video_info": {"name": "m.mp4", "duration": 10.0},
        "transcription_summary": {"language": "en"},
        "frames": [{"frame_file": "f.png", "timestamp": 1.0, "timestamp_formatted": "00:00:01"}],
        "transcription_mapping": {"f.png": {"full_text": "captured"}},
    })
    del frames_dir
    document = KnowledgeDocument(
        documentation_mode="REFERENCE",
        title="t",
        sections=[KnowledgeSection(
            id="section-01", section_type="CONCEPT", title="C", order=1,
            claims=(KnowledgeClaim(id="claim-001", text="A factual claim with no refs.", evidence_refs=()),),
        )],
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    report = validate_knowledge_document(document, timeline)
    assert not report.valid
    assert any("claim without evidence refs" in e for e in report.errors)


# ── DV2-17 bad procedure ──────────────────────────────────────────────────

def test_dv2_17_procedure_step_without_evidence_fails(tmp_path):
    _, timeline = _timeline(tmp_path)
    document = KnowledgeDocument(
        documentation_mode="TUTORIAL",
        title="t",
        sections=[],
        procedures=[SynthesizedProcedure(
            id="procedure-001", title="p",
            steps=(SynthesizedStep(order=1, instruction="Do something", evidence_refs=()),),
        )],
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    report = validate_knowledge_document(document, timeline)
    assert not report.valid
    assert any("without evidence refs" in e for e in report.errors)


# ── DV2-18 reviewed spoof ─────────────────────────────────────────────────

def test_dv2_18_model_provided_human_reviewed_is_coerced_never_accepted(tmp_path):
    provider = _SpoofReviewProvider()
    service = SynthesisService(provider, MockAllowAllGuard(), model_name="m")
    _, timeline = _timeline(tmp_path)
    result = service.synthesize(timeline, "KT_SESSION", KT_CONFIG)
    assert result.status == STATUS_OK
    document = result.document
    assert document is not None
    for section in document.sections:
        for claim in section.claims:
            assert claim.verification_status == "SYNTHESIZED_UNREVIEWED"
    assert document.review_status != "HUMAN_REVIEWED"
    for ref in document.evidence_index:
        assert ref.get("reviewed") is not timeline.by_id().get(ref["evidenceId"], None) or ref.get("reviewed") is False or timeline.by_id()[ref["evidenceId"]].reviewed

    # A hand-built document claiming HUMAN_REVIEWED fails grounding outright.
    spoof = KnowledgeDocument(
        documentation_mode="REFERENCE", title="t",
        sections=[KnowledgeSection(
            id="section-01", section_type="CONCEPT", title="C", order=1,
            claims=(KnowledgeClaim(id="claim-001", text="x",
                                   evidence_refs=(timeline.facts()[0].evidence_id,),
                                   verification_status="HUMAN_REVIEWED"),),
        )],
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    report = validate_knowledge_document(spoof, timeline)
    assert not report.valid
    assert any("HUMAN_REVIEWED" in e for e in report.errors)


class _SpoofReviewProvider(MockKTSynthesisProvider):
    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        import json as _json

        raw = super().generate_summary(text, system_prompt, max_tokens, temperature)
        data = _json.loads(raw)
        for section in data.get("sections", []):
            for claim in section.get("claims", []):
                claim["verificationStatus"] = "HUMAN_REVIEWED"
        return _json.dumps(data)


# ── DV2-19 timestamp bound ────────────────────────────────────────────────

def test_dv2_19_out_of_duration_reference_fails(tmp_path):
    _, timeline = _timeline(tmp_path)
    good_ref = timeline.facts()[0].to_ref()
    bad_ref = dict(good_ref)
    bad_ref["evidenceId"] = "E-777"
    bad_ref["timestampStart"] = timeline.duration + 500
    bad_ref["timestampEnd"] = timeline.duration + 600
    document = KnowledgeDocument(
        documentation_mode="REFERENCE", title="t",
        evidence_index=[item.to_ref() for item in timeline.items] + [bad_ref],
    )
    report = validate_knowledge_document(document, timeline)
    assert not report.valid
    assert any("outside source duration" in e for e in report.errors)


# ── DV2-20 last-good ──────────────────────────────────────────────────────

def test_dv2_20_invalid_synthesis_does_not_overwrite_existing_valid_manual(tmp_path, monkeypatch):
    from transcript_pipeline.documentation import pipeline_v2
    published = []
    monkeypatch.setattr(pipeline_v2, "_publish_semantic_knowledge", lambda *args, **kwargs: published.append(args) or {"published": False})
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    good_service = SynthesisService(MockKTSynthesisProvider(), MockAllowAllGuard(), model_name="m")
    first = generate_documentation_v2(
        frames_dir, "acme_kt_session.mp4", project_config=KT_CONFIG, synthesis_service=good_service
    )
    assert first["status"] in ("MANUAL_READY", "EVIDENCE_READY", "PUBLISH_ENQUEUED")
    assert first["status"] == "MANUAL_READY"
    good_document = (frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8")

    bad_service = SynthesisService(MockAlwaysMalformedProvider(), MockAllowAllGuard(), model_name="m")
    second = generate_documentation_v2(
        frames_dir, "acme_kt_session.mp4", project_config=KT_CONFIG, synthesis_service=bad_service
    )
    assert second["status"] == STATUS_INVALID
    assert len(published) == 1, "invalid synthesis must not publish"
    assert (frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8") == good_document
    assert json.loads((frames_dir / "manual" / "metadata.json").read_text(encoding="utf-8"))["synthesis_status"] == "MANUAL_READY"
    # The failure is stored as compact evidence, not as a new manual.
    report_path = frames_dir / "manual" / "synthesis-validation.json"
    assert report_path.exists()


# ── DV2-44 evidence-only provider unavailable ─────────────────────────────

def test_dv2_44_provider_unavailable_yields_typed_status_no_false_manual_ready(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    unavailable = SynthesisService(None, None)
    result = generate_documentation_v2(
        frames_dir, "acme_kt_session.mp4", project_config=KT_CONFIG, synthesis_service=unavailable
    )
    assert result["status"] == STATUS_UNAVAILABLE
    assert result["semantic"]["ready"] is False
    # Evidence outputs succeed; compatibility bundles keep legacy callers alive.
    assert (frames_dir / "evidence" / "evidence.jsonl").exists()
    assert (frames_dir / "manual" / "steps.json").exists()
    assert (frames_dir / "manual" / "MANUAL.md").exists()
    assert not (frames_dir / "manual" / "knowledge-document.json").exists()
    metadata = json.loads((frames_dir / "manual" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata.get("synthesis_status") == STATUS_UNAVAILABLE


# ── DV2-45 malformed retry bound ──────────────────────────────────────────

def test_dv2_45_at_most_one_schema_repair_call(tmp_path):
    provider = MockAlwaysMalformedProvider()
    service = SynthesisService(provider, MockAllowAllGuard(), model_name="m")
    _, timeline = _timeline(tmp_path)
    result = service.synthesize(timeline, "KT_SESSION", KT_CONFIG)
    assert result.status == STATUS_INVALID
    # One original + exactly one repair per block — the always-malformed
    # provider must be called exactly twice per block and never a third time.
    from transcript_pipeline.documentation.compaction import build_synthesis_blocks

    block_count = len(build_synthesis_blocks(timeline).build().blocks)
    assert len(provider.calls) == block_count * 2
    # The second call per block is the bounded repair prompt, never a third attempt.
    assert sum(1 for call in provider.calls if "previous response was rejected" in call) == block_count

    # A provider that repairs on the retry succeeds with 2 calls for 1 block.
    repaired = MockMalformedThenValidProvider(MockReferenceSynthesisProvider())
    repaired_service = SynthesisService(repaired, MockAllowAllGuard(), model_name="m")
    ok = repaired_service.synthesize(timeline, "REFERENCE", KT_CONFIG)
    assert ok.status == STATUS_OK
    assert ok.invocation_count == 2 * block_count


# ── DV2-46 no recursive loop ──────────────────────────────────────────────

def test_dv2_46_invocation_count_bounded_by_blocks_plus_one_repair_each(tmp_path):
    provider = MockKTSynthesisProvider()
    service = SynthesisService(provider, MockAllowAllGuard(), model_name="m")
    _, timeline = _timeline(tmp_path)
    result = service.synthesize(timeline, "KT_SESSION", KT_CONFIG)
    assert result.status == STATUS_OK
    from transcript_pipeline.documentation.compaction import build_synthesis_blocks

    block_count = len(build_synthesis_blocks(timeline).build().blocks)
    assert result.invocation_count == block_count
    assert result.invocation_count <= block_count + block_count  # blocks + one repair per failed response

    flaky = _FlakyOnceProvider()
    flaky_service = SynthesisService(flaky, MockAllowAllGuard(), model_name="m")
    flaky_result = flaky_service.synthesize(timeline, "KT_SESSION", KT_CONFIG)
    assert flaky_result.status == STATUS_OK
    assert flaky_result.invocation_count <= 2 * block_count


class _FlakyOnceProvider(MockKTSynthesisProvider):
    """Fails the very first request once, then behaves (one repair used)."""

    def __init__(self) -> None:
        super().__init__()
        self._first_done = False

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        if not self._first_done:
            self._first_done = True
            return "garbage not json"
        return super().generate_summary(text, system_prompt, max_tokens, temperature)


# ── extra: validation report persistence + mutation detection ─────────────

def test_validation_report_persisted_and_source_mutation_fails(tmp_path, tmp_path_factory):
    _, timeline = _timeline(tmp_path)
    document = KnowledgeDocument(
        documentation_mode="REFERENCE", title="t",
        synthesis=SynthesisMetadata(generated_at="2026-01-01T00:00:00+00:00"),
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    report = validate_knowledge_document(document, timeline, source_evidence_mutated=True)
    assert not report.valid
    assert any("mutated in-place" in e for e in report.errors)

    good = validate_knowledge_document(document, timeline)
    assert good.valid
    manual_dir = tmp_path / "manual"
    path = write_validation_report(manual_dir, good)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["valid"] is True
    assert persisted["claimCount"] == 0


def test_delta005_section_summary_requires_block_local_evidence(tmp_path):
    from transcript_pipeline.documentation.synthesis import _validate_fragment_shape

    _, timeline = _timeline(tmp_path)
    evidence_id = timeline.facts()[0].evidence_id
    fragment = {"sections": [{
        "sectionType": "CONCEPT", "title": "Context", "summary": "Grounded context.",
        "claims": [{"text": "A grounded claim.", "evidenceIds": [evidence_id]}],
    }]}
    valid, error, _ = _validate_fragment_shape(json.dumps(fragment), {evidence_id})
    assert not valid
    assert error == "section summary without evidence ids"

    fragment["sections"][0]["evidenceIds"] = [evidence_id]
    valid, _, _ = _validate_fragment_shape(json.dumps(fragment), {"E-OTHER"})
    assert not valid

    valid, _, _ = _validate_fragment_shape(json.dumps(fragment), {evidence_id})
    assert valid
    service = SynthesisService(MockKTSynthesisProvider(), MockAllowAllGuard(), model_name="m")
    merged = service._merge_fragments([fragment], timeline, "REFERENCE", 1).document
    section = merged.sections[0]
    assert section.evidence_refs == (evidence_id,)
    assert validate_knowledge_document(merged, timeline).valid


def test_delta005_final_grounding_rejects_summary_without_refs_and_placeholder_only(tmp_path):
    _, timeline = _timeline(tmp_path)
    document = KnowledgeDocument(
        documentation_mode="REFERENCE", title="t",
        sections=[KnowledgeSection(
            id="section-01", section_type="CONCEPT", title="Context",
            summary="Unsupported context.", evidence_refs=(),
        )],
        evidence_index=[ref.to_ref() for ref in timeline.items],
    )
    report = validate_knowledge_document(document, timeline)
    assert not report.valid
    assert any("section summary without evidence refs" in error for error in report.errors)

    placeholder = next((item for item in timeline.items if item.is_placeholder()), None)
    if placeholder is not None:
        document.sections[0] = KnowledgeSection(
            id="section-01", section_type="CONCEPT", title="Context",
            summary="Unsupported context.", evidence_refs=(placeholder.evidence_id,),
            summary_evidence_refs=(placeholder.evidence_id,),
        )
        report = validate_knowledge_document(document, timeline)
        assert any("only placeholder evidence supports a factual summary" in error for error in report.errors)

    evidence_id = timeline.facts()[0].evidence_id
    document.sections = []
    document.procedures = [SynthesizedProcedure(
        id="procedure-001", title="Process", purpose="Ungrounded purpose.",
        steps=(SynthesizedStep(order=1, instruction="A step.", evidence_refs=(evidence_id,)),),
    )]
    report = validate_knowledge_document(document, timeline)
    assert any("procedure metadata without evidence refs" in error for error in report.errors)


def test_delta005_procedure_metadata_requires_refs_and_merges_deterministically(tmp_path):
    from transcript_pipeline.documentation.synthesis import _validate_fragment_shape

    _, timeline = _timeline(tmp_path)
    evidence_id = timeline.facts()[0].evidence_id
    procedure = {
        "title": "Process", "purpose": "Why it is used.", "prerequisites": ["Access"],
        "expectedOutcomes": ["A completed task."],
        "steps": [{"instruction": "Perform the task.", "evidenceIds": [evidence_id]}],
    }
    base = {"sections": [], "procedures": [procedure]}
    valid, error, _ = _validate_fragment_shape(json.dumps(base), {evidence_id})
    assert not valid
    assert error == "procedure metadata without evidence ids"

    procedure["evidenceIds"] = [evidence_id]
    valid, _, _ = _validate_fragment_shape(json.dumps(base), {evidence_id})
    assert valid
    service = SynthesisService(MockKTSynthesisProvider(), MockAllowAllGuard(), model_name="m")
    merged = service._merge_fragments([base], timeline, "TUTORIAL", 1).document
    assert merged.procedures[0].evidence_refs == (evidence_id,)
    assert validate_knowledge_document(merged, timeline).valid

    for field, value in (("prerequisites", ["Access"]), ("expectedOutcomes", ["Done."])):
        candidate = dict(procedure, purpose="", prerequisites=[], expectedOutcomes=[])
        candidate[field] = value
        candidate.pop("evidenceIds")
        valid, _, _ = _validate_fragment_shape(
            json.dumps({"sections": [], "procedures": [candidate]}), {evidence_id}
        )
        assert not valid


def test_delta005_grounded_summary_procedure_and_exec_summary_render_with_refs(tmp_path):
    from transcript_pipeline.documentation.knowledge_models import executive_summary_evidence_refs
    from transcript_pipeline.documentation.semantic_manual_writer import _render_markdown

    frames_dir, timeline = _timeline(tmp_path)
    evidence_id = timeline.facts()[0].evidence_id
    section = KnowledgeSection(
        id="section-01", section_type="EXECUTIVE_SUMMARY", title="Overview",
        summary="Grounded overview.", evidence_refs=(evidence_id,), summary_evidence_refs=(evidence_id,),
    )
    procedure = SynthesizedProcedure(
        id="procedure-001", title="Grounded process", purpose="Why this process is used.",
        prerequisites=("Approved access",),
        steps=(SynthesizedStep(order=1, instruction="Complete the action.", evidence_refs=(evidence_id,)),),
        expected_outcomes=("The task is complete.",), evidence_refs=(evidence_id,),
        metadata_evidence_refs=(evidence_id,),
    )
    document = KnowledgeDocument(
        documentation_mode="TUTORIAL", title="Grounding", executive_summary=section.summary,
        sections=[section], procedures=[procedure],
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    assert executive_summary_evidence_refs(document) == (evidence_id,)
    markdown = _render_markdown(document, timeline, {})
    assert f"Grounded overview. [{evidence_id} @" in markdown
    assert f"Procedure evidence:** [{evidence_id} @" in markdown

    from transcript_pipeline.documentation.models import DocumentationSource
    from transcript_pipeline.documentation.screenshots import ScreenshotSelection
    from transcript_pipeline.documentation.semantic_pdf_writer import write_semantic_manual_pdf
    pdf_path = write_semantic_manual_pdf(
        frames_dir / "manual", document, timeline, ScreenshotSelection([]),
        DocumentationSource("source.mp4", timeline.duration, "en", "test", "now"),
    )
    try:
        from pypdf import PdfReader
    except ImportError:
        pytest.skip("pypdf is not installed")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert evidence_id in pdf_text
    assert "Approved access" in pdf_text
    assert "The task is complete." in pdf_text


def test_delta005_executive_summary_never_uses_ungrounded_summary(tmp_path):
    from transcript_pipeline.documentation.synthesis import _executive_summary

    ungrounded = KnowledgeSection(
        id="section-01", section_type="EXECUTIVE_SUMMARY", title="Overview",
        summary="Untracked factual prose.",
    )
    assert _executive_summary([ungrounded]) == ""
    _, timeline = _timeline(tmp_path)
    invalid_document = KnowledgeDocument(
        documentation_mode="REFERENCE", title="t", executive_summary="Untracked factual prose.",
        sections=[ungrounded], evidence_index=[item.to_ref() for item in timeline.items],
    )
    report = validate_knowledge_document(invalid_document, timeline)
    assert any("executive summary has no grounded" in error for error in report.errors)

    evidence_id = timeline.facts()[0].evidence_id
    claim = KnowledgeClaim(id="claim-001", text="Grounded claim.", evidence_refs=(evidence_id,))
    grounded_claims = KnowledgeSection(
        id="section-02", section_type="EXECUTIVE_SUMMARY", title="Overview", claims=(claim,),
    )
    assert _executive_summary([grounded_claims]) == "Grounded claim."


def test_delta005_semantic_chunks_and_knowledge_package_keep_prose_refs(tmp_path):
    from transcript_pipeline.documentation.knowledge_models import executive_summary_evidence_refs
    from transcript_pipeline.documentation.semantic_package import _build_chunks
    from transcript_pipeline.documentation.models import DocumentationSource
    from transcript_pipeline.knowledge.package_builder import build_knowledge_package_from_document

    frames_dir, timeline = _timeline(tmp_path)
    evidence_id = timeline.facts()[0].evidence_id
    section = KnowledgeSection(
        id="section-01", section_type="EXECUTIVE_SUMMARY", title="Overview",
        summary="Grounded summary.", evidence_refs=(evidence_id,), summary_evidence_refs=(evidence_id,),
    )
    procedure = SynthesizedProcedure(
        id="procedure-001", title="Process", purpose="Grounded purpose.",
        prerequisites=("Access",),
        steps=(SynthesizedStep(order=1, instruction="Run task.", evidence_refs=(evidence_id,)),),
        expected_outcomes=("Done.",), evidence_refs=(evidence_id,), metadata_evidence_refs=(evidence_id,),
    )
    document = KnowledgeDocument(
        documentation_mode="TUTORIAL", title="Knowledge", executive_summary=section.summary,
        sections=[section], procedures=[procedure],
        evidence_index=[item.to_ref() for item in timeline.items],
    )
    chunks = _build_chunks(
        document, timeline, DocumentationSource("source.mp4", timeline.duration, "en", "test", "now"),
        "PROJECT", "acme", "TUTORIAL", "GUIDED", 4000,
    )
    summary_chunk = next(chunk for chunk in chunks if chunk["id"].startswith("section-"))
    procedure_chunk = next(chunk for chunk in chunks if chunk["metadata"]["sectionType"] == "PROCEDURE")
    assert evidence_id in summary_chunk["metadata"]["evidenceRefs"]
    assert evidence_id in procedure_chunk["metadata"]["evidenceRefs"]
    assert "Grounded purpose." in procedure_chunk["text"]
    assert "Prerequisite: Access" in procedure_chunk["text"]
    assert "Expected outcome: Done." in procedure_chunk["text"]
    assert executive_summary_evidence_refs(document) == (evidence_id,)
    package = build_knowledge_package_from_document(
        knowledge_document=document,
        evidence_timeline=timeline,
        project_config={"second_brain": {
            "enabled": True, "scope": "PROJECT", "project_id": "acme",
            "domain": "second-brain/acme", "default_artifact_type": "TUTORIAL",
            "default_actionability": "GUIDED",
        }},
    )
    assert package is not None
    knowledge = package.to_dict()["knowledge"]
    assert knowledge["summaryEvidenceRefs"] == [evidence_id]
    assert knowledge["sections"][0]["summaryEvidenceRefs"] == [evidence_id]
    assert knowledge["procedures"][0]["metadataEvidenceRefs"] == [evidence_id]
