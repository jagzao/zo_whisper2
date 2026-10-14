"""Synthesis domain models for V2.

KnowledgeClaim, KnowledgeSection, SynthesizedProcedure, KnowledgeDocument.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SectionType = Literal[
    "EXECUTIVE_SUMMARY",
    "CONTEXT_SCOPE",
    "GOAL",
    "PREREQUISITES",
    "CONCEPT",
    "PROCESS",
    "PROCEDURE",
    "SYSTEM",
    "ROLE_RESPONSIBILITY",
    "DECISION",
    "RISK",
    "OPEN_QUESTION",
    "ACTION_ITEM",
    "TROUBLESHOOTING",
    "ARCHITECTURE_COMPONENT",
    "DEPENDENCY",
    "DATA_FLOW",
    "EXPECTED_RESULT",
    "GLOSSARY",
    "REFERENCE",
]

VerificationStatus = Literal["SYNTHESIZED_UNREVIEWED", "HUMAN_REVIEWED"]
Actionability = Literal["REFERENCE", "GUIDED", "EXECUTABLE"]


@dataclass(frozen=True)
class KnowledgeClaim:
    id: str
    text: str
    evidenceRefs: list[str]  # REQUIRED non-empty
    evidenceConfidence: Literal["high", "medium", "low"]
    verificationStatus: VerificationStatus
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class KnowledgeSection:
    id: str
    sectionType: SectionType
    title: str
    summary: str
    claims: list[KnowledgeClaim]
    evidenceRefs: list[str]
    screenshotCandidates: list[str]
    order: int


@dataclass(frozen=True)
class SynthesizedProcedureStep:
    order: int
    instruction: str
    evidenceRefs: list[str]  # REQUIRED non-empty
    semanticAction: str | None = None
    semanticTarget: str | None = None


@dataclass(frozen=True)
class SynthesizedProcedure:
    id: str
    title: str
    purpose: str
    prerequisites: list[str]
    steps: list[SynthesizedProcedureStep]
    expectedOutcomes: list[str]
    evidenceRefs: list[str]
    actionability: Actionability


@dataclass(frozen=True)
class SynthesisMetadata:
    providerType: str
    model: str
    generatedAt: datetime
    status: Literal["success", "invalid", "blocked"]
    inputHash: str


@dataclass(frozen=True)
class KnowledgeDocument:
    schemaVersion: int = 2
    source: dict = field(default_factory=dict)
    documentationMode: str = ""
    title: str = ""
    purpose: str | None = None
    executiveSummary: str = ""
    sections: list[KnowledgeSection] = field(default_factory=list)
    procedures: list[SynthesizedProcedure] = field(default_factory=list)
    glossary: list[dict] = field(default_factory=list)
    evidenceIndex: list[dict] = field(default_factory=list)
    synthesis: SynthesisMetadata | None = None
    reviewStatus: str = "UNREVIEWED"