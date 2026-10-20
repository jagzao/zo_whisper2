"""Deterministic synthetic fixtures for Documentation Synthesis V2 tests.

All content is SYNTHETIC: organizations (Acme Corp), applications
(GadgetPlus, NimbusDesk, FlowDesk), people (roles only) and repositories.
No real client names, screenshots or transcripts (AC-21, DV2-48).

Running this module regenerates the committed `*_frame_mapping.json`
fixtures byte-identically (deterministic construction, no timestamps).

Fixture shapes:
- kt_session       — 45 frames / 75 min: context, concepts, systems,
                     process, roles, decisions, risks, open questions,
                     actions; repeated OCR runs; low-confidence tail;
- tutorial         — 12 frames: explicit ordered operational actions;
- reference_meeting — 8 frames: reference discussion, no ordered actions.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent


def _frame(name: str, timestamp: float) -> dict:
    h, r = divmod(int(timestamp), 3600)
    m, s = divmod(r, 60)
    return {
        "frame_file": name,
        "timestamp": timestamp,
        "timestamp_formatted": f"{h:02d}:{m:02d}:{s:02d}",
    }


def _mapping(name: str, duration: float, frames: list[dict], mapping: dict, transcript: str) -> dict:
    return {
        "video_info": {
            "name": name,
            "duration": duration,
            "extraction_method": "smart_scene",
            "total_frames": len(frames),
        },
        "transcription_summary": {
            "total_segments": sum(
                len(entry.get("transcription_segments", [])) for entry in mapping.values()
            ),
            "mapped_frames": len([e for e in mapping.values() if e.get("transcription_segments")]),
            "full_transcription": transcript,
            "language": "en",
        },
        "frames": frames,
        "transcription_mapping": mapping,
    }


def _entry(timestamp: float, text: str | None, segments: list[dict] | None = None) -> dict:
    return {
        "timestamp": timestamp,
        "formatted_timestamp": f"{int(timestamp // 60):02d}:{int(timestamp % 60):02d}",
        "transcription_segments": segments or [],
        "full_text": text or "",
    }


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text, "avg_logprob": -0.2}


KT_LINES = [
    (100, "Welcome to the NimbusDesk support onboarding knowledge transfer for Acme Corp."),
    (200, "Today we cover the GadgetPlus application support model end to end."),
    (300, "Our scope includes ticket triage, escalation and reporting for GadgetPlus."),
    (400, "First, the core concepts behind the GadgetPlus service catalog."),
    (500, "GadgetPlus exposes three modules: orders, billing and returns."),
    (600, "The FlowDesk ITSM tool is the single system of record for tickets."),
    (700, "Compliance requires every ticket to carry the customer consent flag."),
    (800, "Now the daily process. Start by opening the NimbusDesk dashboard."),
    (900, "Triage new tickets before ten in the morning using the queue view."),
    (1000, "Priority one incidents follow the fifteen minute acknowledgement rule."),
    (1100, "Escalate to level two when the knowledge base has no matching article."),
    (1200, "The escalation matrix lives in the FlowDesk configuration module."),
    (1300, "Weekly we reconcile the returns queue against the billing report."),
    (1400, "Monthly compliance sampling pulls twenty random consent flags."),
    (1500, "Roles and responsibilities. Level one owns triage and first response."),
    (1600, "Level two owns deep diagnostics and vendor coordination for GadgetPlus."),
    (1700, "The knowledge owner curates the shared article repository."),
    (1800, "Shadowing happens in the first two weeks of the transition."),
    (1900, "Reverse shadow starts in week three with the new owner driving."),
    (2000, "Decisions. We agreed tickets keep the Acme Corp standard naming scheme."),
    (2100, "The backup owner for billing queries is the returns specialist."),
    (2200, "Reporting cadence moves to a single weekly digest every Friday."),
    (2300, "Risks. Peak season load may double the returns queue volume."),
    (2400, "The FlowDesk license expires during the transition window."),
    (2500, "Open question: who owns the legacy returns archive after cutover?"),
    (2600, "Action items. Complete the support checklist before shadow week."),
    (2700, "Schedule the reverse shadow sessions with the service lead."),
    (2800, "Publish the glossary of GadgetPlus terms to the repository."),
    (2900, "That closes the knowledge transfer session. Thank you all."),
]

KT_REPEATED_OCR = {
    # Near-identical dashboard screens captured on consecutive frames:
    800: "NimbusDesk Dashboard - Queue View (127 pending)",
    900: "NimbusDesk Dashboard - Queue View (127 pending)",
    1000: "NimbusDesk Dashboard - Queue View (127 pending)",
    # Escalation matrix screens:
    1100: "FlowDesk > Escalation Matrix (P1 15m / P2 4h)",
    1200: "FlowDesk > Escalation Matrix (P1 15m / P2 4h)",
    # Single unique screens:
    500: "GadgetPlus Modules: Orders | Billing | Returns",
    1400: "Compliance Sampling - Consent Flags",
    1800: "Shadow Schedule Weeks 1-2 - Acme Corp",
}


def build_kt_fixture() -> tuple[dict, dict[str, str]]:
    frames = []
    mapping = {}
    transcript_lines = []
    ocr_by_frame: dict[str, str] = {}
    # 45 frames over 75 minutes; content frames at 100..2900s, then a
    # low-confidence tail with no transcript and no OCR (40..44).
    content_timestamps = [line[0] for line in KT_LINES]
    tail_timestamps = [3000 + i * 200 for i in range(5)]
    all_timestamps = content_timestamps + tail_timestamps + [
        t for t in (150, 250, 350, 450, 550, 650, 750, 850, 950, 1050, 1150, 1250,
                    1350, 1450, 1550, 1650, 1750, 1850, 1950, 2050, 2150, 2250, 2350,
                    2450, 2550, 2650, 2750, 2850)
    ]
    all_timestamps = sorted(set(all_timestamps))[:45]

    for index, timestamp in enumerate(all_timestamps):
        frame = _frame(f"frame_{index:04d}.png", float(timestamp))
        frames.append(frame)
        line = next((l for l in KT_LINES if l[0] == timestamp), None)
        if timestamp in KT_REPEATED_OCR:
            ocr_by_frame[frame["frame_file"]] = KT_REPEATED_OCR[timestamp]
        if line:
            text = line[1]
            mapping[frame["frame_file"]] = _entry(
                float(timestamp), text,
                [_seg(timestamp - 3.0, timestamp + 7.0, text)],
            )
            transcript_lines.append(text)
        else:
            mapping[frame["frame_file"]] = _entry(float(timestamp), None)

    return _mapping(
        "acme_kt_session.mp4",
        4500.0,
        frames,
        mapping,
        " ".join(transcript_lines) + " Welcome again to the Acme Corp knowledge transfer program closing remarks.",
    ), ocr_by_frame


TUTORIAL_STEPS = [
    (30, "First, open GadgetPlus and click the New Project button."),
    (90, "Type the project name Acme Demo and pick the Orders module."),
    (150, "Press Enter to confirm and open the project workspace."),
    (210, "Select Import Data from the toolbar and choose the CSV option."),
    (270, "Browse to the sample file and click Open to start the import."),
    (330, "Wait for the validation badge to turn green before continuing."),
    (390, "Click Map Fields and match the returns column to Returns ID."),
    (450, "Press Run Import and watch the progress bar finish."),
    (510, "Open the Reports tab and select the Weekly Digest template."),
    (570, "Finally, click Export to save the digest as a PDF file."),
]

TUTORIAL_OCR = {
    30: "GadgetPlus - [New Project]",
    210: "Import Data > CSV",
    270: "sample_returns.csv - Open",
    390: "Map Fields: returns -> Returns ID",
    510: "Reports > Weekly Digest",
}


def build_tutorial_fixture() -> tuple[dict, dict[str, str]]:
    frames = []
    mapping = {}
    lines = []
    ocr_by_frame: dict[str, str] = {}
    for index, (timestamp, text) in enumerate(TUTORIAL_STEPS):
        frame = _frame(f"frame_{index:04d}.png", float(timestamp))
        frames.append(frame)
        mapping[frame["frame_file"]] = _entry(
            float(timestamp), text, [_seg(timestamp - 2.0, timestamp + 8.0, text)]
        )
        if timestamp in TUTORIAL_OCR:
            ocr_by_frame[frame["frame_file"]] = TUTORIAL_OCR[timestamp]
        lines.append(text)
    # Two silent frames (review queue tail).
    for index, timestamp in enumerate((630.0, 660.0), start=len(TUTORIAL_STEPS)):
        frame = _frame(f"frame_{index:04d}.png", timestamp)
        frames.append(frame)
        mapping[frame["frame_file"]] = _entry(timestamp, None)
    return _mapping("gadgetplus_tutorial.mp4", 700.0, frames, mapping, " ".join(lines)), ocr_by_frame


REFERENCE_LINES = [
    (60, "This session is a reference overview of the Acme Corp data platforms."),
    (140, "The metrics warehouse feeds the NimbusDesk and FlowDesk dashboards."),
    (220, "Repository access is granted through the Acme Corp identity portal."),
    (300, "Historical dashboards remain read-only after each quarter closes."),
    (380, "The glossary of platform terms is maintained by the data steward."),
    (460, "Reference links to the archive are published in the team wiki."),
    (540, "Any further questions should go to the service desk queue."),
]


def build_reference_fixture() -> tuple[dict, dict[str, str]]:
    frames = []
    mapping = {}
    lines = []
    for index, (timestamp, text) in enumerate(REFERENCE_LINES):
        frame = _frame(f"frame_{index:04d}.png", float(timestamp))
        frames.append(frame)
        mapping[frame["frame_file"]] = _entry(
            float(timestamp), text, [_seg(timestamp - 3.0, timestamp + 7.0, text)]
        )
        lines.append(text)
    return _mapping("acme_reference_overview.mp4", 600.0, frames, mapping, " ".join(lines)), {}


BUILDERS = {
    "kt_session_frame_mapping.json": build_kt_fixture,
    "tutorial_frame_mapping.json": build_tutorial_fixture,
    "reference_meeting_frame_mapping.json": build_reference_fixture,
}


def regenerate() -> None:
    for filename, builder in BUILDERS.items():
        path = FIXTURES_DIR / filename
        path.write_text(json.dumps(builder()[0], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path.name}")


if __name__ == "__main__":
    regenerate()
