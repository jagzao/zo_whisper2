"""Mock synthesis providers for deterministic V2 tests (PLAN WP-18).

Frozen structured JSON only â€” no LLM, no network. The mocks cite REAL
evidence ids parsed from the deterministic request payload so grounding
validation passes/fails exactly as the test intends.
"""
from __future__ import annotations

import json

from transcript_pipeline.llm.provider import LLMProviderType


class _BaseMock:
    provider_type = LLMProviderType.LOCAL  # local => never privacy-blocked

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._last_catalog_ids: list[str] = []

    def _catalog_ids_tolerant(self, text: str) -> list[str]:
        """Parses the evidence ids from the request payload. A repair retry
        sends a plain-text repair prompt instead — the last known catalog is
        reused (single-threaded deterministic test flow)."""
        try:
            ids = _catalog_ids(text)
        except ValueError:
            return self._last_catalog_ids
        self._last_catalog_ids = ids
        return ids


class MockAllowAllGuard:
    def check(self, provider, project_config=None) -> None:
        return None


class MockDenyGuard:
    def check(self, provider, project_config=None) -> None:
        raise PermissionError("blocked by mock guard")


def _catalog_ids(user_payload_text: str) -> list[str]:
    payload = json.loads(user_payload_text)
    return [entry["evidenceId"] for entry in payload.get("evidenceCatalog", [])]


class MockKTSynthesisProvider(_BaseMock):
    """Frozen KT_SESSION response: summary/context/process/system/roles/
    decision/risk/open-question/action sections, NO procedure (DV2-24/35)."""

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        self.calls.append(text)
        ids = self._catalog_ids_tolerant(text)
        e = lambda i: ids[i] if i < len(ids) else (ids[-1] if ids else "E-001")  # noqa: E731
        return json.dumps({
            "sections": [
                {"sectionType": "EXECUTIVE_SUMMARY", "title": "Session summary",
                 "summary": "Knowledge transfer for Acme Corp GadgetPlus application support.",
                 "claims": [{"text": "The session covers the GadgetPlus support model.", "evidenceIds": [e(0)]}]},
                {"sectionType": "CONTEXT_SCOPE", "title": "Scope",
                 "summary": "Ticket triage, escalation and reporting.",
                 "claims": [{"text": "Scope includes ticket triage and escalation.", "evidenceIds": [e(1)]}]},
                {"sectionType": "PROCESS", "title": "Daily process",
                 "summary": "Morning triage and escalation flow.",
                 "claims": [{"text": "Tickets are triaged before ten each morning.", "evidenceIds": [e(2)]}]},
                {"sectionType": "SYSTEM", "title": "Systems",
                 "summary": "",
                 "claims": [{"text": "FlowDesk is the system of record for tickets.", "evidenceIds": [e(3)]}]},
                {"sectionType": "ROLE_RESPONSIBILITY", "title": "Roles",
                 "summary": "",
                 "claims": [{"text": "Level one owns triage and first response.", "evidenceIds": [e(4)]}]},
                {"sectionType": "DECISION", "title": "Decisions",
                 "summary": "",
                 "claims": [{"text": "Tickets keep the standard naming scheme.", "evidenceIds": [e(5)]}]},
                {"sectionType": "RISK", "title": "Risks",
                 "summary": "",
                 "claims": [{"text": "Peak season may double the returns queue.", "evidenceIds": [e(6)]}]},
                {"sectionType": "OPEN_QUESTION", "title": "Open questions",
                 "summary": "",
                 "claims": [{"text": "Legacy returns archive ownership is unresolved.", "evidenceIds": [e(7)]}]},
                {"sectionType": "ACTION_ITEM", "title": "Action items",
                 "summary": "",
                 "claims": [{"text": "Complete the support checklist before shadow week.", "evidenceIds": [e(8)]}]},
            ],
            "procedures": [],
            "glossary": [{"term": "Shadow", "definition": "Observation period during transition.",
                          "evidenceIds": [e(9)]}],
        })


class MockTutorialSynthesisProvider(_BaseMock):
    """Frozen TUTORIAL response with an ordered, grounded procedure (DV2-25)."""

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        self.calls.append(text)
        ids = self._catalog_ids_tolerant(text)
        e = lambda i: ids[i] if i < len(ids) else (ids[-1] if ids else "E-001")  # noqa: E731
        return json.dumps({
            "sections": [
                {"sectionType": "GOAL", "title": "Goal",
                 "summary": "Import sample data into a GadgetPlus project and export a digest.",
                 "claims": [{"text": "The tutorial imports data and exports a weekly digest.", "evidenceIds": [e(0)]}]},
                {"sectionType": "PREREQUISITES", "title": "Prerequisites",
                 "summary": "",
                 "claims": [{"text": "A GadgetPlus account with project rights is required.", "evidenceIds": [e(0)]}]},
                {"sectionType": "PROCEDURE", "title": "Import procedure",
                 "summary": "Ordered steps from the recording.",
                 "claims": [{"text": "The import requires field mapping before running.", "evidenceIds": [e(4)]}]},
                {"sectionType": "EXPECTED_RESULT", "title": "Result",
                 "summary": "",
                 "claims": [{"text": "A weekly digest PDF is exported.", "evidenceIds": [e(9)]}]},
            ],
            "procedures": [
                {"title": "Import data and export the weekly digest",
                 "purpose": "Standard GadgetPlus reporting flow.",
                 "prerequisites": ["GadgetPlus project rights"],
                 "steps": [
                     {"instruction": "Click the New Project button.", "evidenceIds": [e(0)]},
                     {"instruction": "Type the project name and pick the Orders module.", "evidenceIds": [e(1)]},
                     {"instruction": "Press Enter to open the workspace.", "evidenceIds": [e(2)]},
                     {"instruction": "Select Import Data and choose CSV.", "evidenceIds": [e(3)]},
                     {"instruction": "Map the returns column and run the import.", "evidenceIds": [e(4)]},
                     {"instruction": "Open Reports and export the Weekly Digest as PDF.", "evidenceIds": [e(9)]},
                 ],
                 "expectedOutcomes": ["A weekly digest PDF exists in the project."]}
            ],
            "glossary": [],
        })


class MockReferenceSynthesisProvider(_BaseMock):
    """Frozen REFERENCE response with zero procedures (DV2-26)."""

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        self.calls.append(text)
        ids = self._catalog_ids_tolerant(text)
        e = lambda i: ids[i] if i < len(ids) else (ids[-1] if ids else "E-001")  # noqa: E731
        return json.dumps({
            "sections": [
                {"sectionType": "EXECUTIVE_SUMMARY", "title": "Overview",
                 "summary": "Reference overview of Acme Corp data platforms.",
                 "claims": [{"text": "The session references the Acme Corp data platforms.", "evidenceIds": [e(0)]}]},
                {"sectionType": "REFERENCE", "title": "Platforms",
                 "summary": "",
                 "claims": [
                     {"text": "The metrics warehouse feeds NimbusDesk and FlowDesk dashboards.", "evidenceIds": [e(1)]},
                     {"text": "Repository access goes through the identity portal.", "evidenceIds": [e(2)]},
                 ]},
            ],
            "procedures": [],
            "glossary": [],
        })


class MockFreeFormProvider(_BaseMock):
    """Returns free-form Markdown â€” must be rejected (DV2-14)."""

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        self.calls.append(text)
        return "# Session summary\n\nThe team discussed several topics in prose form."


class MockMalformedThenValidProvider(_BaseMock):
    """Malformed on every original request; the schema-repair retry gets the
    valid frozen response (call parity: odd = original, even = repair)."""

    def __init__(self, valid: _BaseMock) -> None:
        self._valid = valid
        self._call_count = 0
        self._last_catalog_ids = []
        # `calls` aliases the valid provider's call log for assertions.
        self.calls = valid.calls

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        self._call_count += 1
        if self._call_count % 2 == 1:
            return "{not valid json at all"
        return self._valid.generate_summary(text, system_prompt, max_tokens, temperature)


class MockAlwaysMalformedProvider(_BaseMock):
    """Every response (original + repair) is malformed â€” bounded calls, no
    recursive repair loop (DV2-45/46)."""

    def generate_summary(self, text, system_prompt=None, max_tokens=2000, temperature=0.3):
        self.calls.append(text)
        return "still not json"
