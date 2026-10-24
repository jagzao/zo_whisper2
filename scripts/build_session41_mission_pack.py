from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as PDFImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from transcript_pipeline.documentation.mission_pack import (
    evaluate_quality_gates,
    measure_source_coverage,
    merge_application_facts,
    validate_claim_records,
)

ROOT = Path(__file__).resolve().parents[1]
VERSION = "000003"
SESSION_ID = "AMS_KAP_-_App_Support_-_Session_41"
FRAME_STEM = "pg_AMS_KAP_-_App_Support_-_Session_41"
SOURCE_VIDEO = ROOT / "Videos/general" / f"{SESSION_ID}.mp4"
PRIMARY_SEGMENTS = ROOT / "CarpetaTranscripciones/general" / f"{SESSION_ID}_segments.json"
TRANSCRIPT_VARIANT = ROOT / "CarpetaTranscripciones/general" / f"pg_{SESSION_ID}_segments.json"
FRAMES_ROOT = ROOT / "CarpetaTranscripciones/general" / f"{FRAME_STEM}_Frames" / FRAME_STEM
RUNTIME_ROOT = ROOT / "CarpetaTranscripciones/general" / f"{FRAME_STEM}_Frames" / FRAME_STEM
OUT = ROOT / ".agents/artifacts/docs-v2/session-41" / f"v{VERSION}"
APP_IDS = {
    "pgregdoc.com": "pgregdoc.com",
    "North America Central Product Research Testing Panelist Payments":
        "north-america-central-product-research-testing-panelist-payments",
}


def claim(cid: str, app: str, text: str, timestamp: str, refs: list[str], *,
          state: str = "SOURCE_CONFIRMED", confidence: str = "HIGH",
          source_type: str = "TRANSCRIPT", conflicts: list[str] | None = None) -> dict[str, Any]:
    item = {
        "id": cid,
        "claim": text,
        "application": app,
        "source_timestamp": timestamp,
        "source_type": source_type,
        "confidence": confidence,
        "verification_state": state,
        "evidence_refs": refs,
        "external_sources": [],
        "conflicts": conflicts or [],
        "text": text,
        "evidenceRefs": refs,
        "evidenceConfidence": confidence.lower(),
        "verificationStatus": "SYNTHESIZED_UNREVIEWED",
        "tags": [state],
    }
    return item


CLAIMS = [
    claim("C-001", "SESSION", "The recording opens by naming two applications: PG RegDoc and North America Central Product Research Testing Panelist Payments.", "00:00:47", ["E-001"]),
    claim("C-002", "pgregdoc.com", "PGRegDoc.com is described as a custom backend hosted on P&G Azure, using SQL and a mail subscription service.", "00:01:26", ["E-002", "V-001"], source_type="TRANSCRIPT+VIDEO_FRAME"),
    claim("C-003", "pgregdoc.com", "The application shares public, non-confidential safety data sheets and technical documents with consumers and customers through an external website.", "00:01:47", ["E-003", "V-001"]),
    claim("C-004", "pgregdoc.com", "The speaker says this document-sharing capability supports business requirements associated with REACH.", "00:01:42", ["E-004"]),
    claim("C-005", "pgregdoc.com", "The speaker says they are not familiar with REACH and offers 'regulations' as their own informal meaning; this definition is not independently confirmed.", "00:01:49", ["E-004"], state="SOURCE_UNCERTAIN", confidence="LOW"),
    claim("C-006", "pgregdoc.com", "The application supports subscriptions and email notifications for updates about available documentation.", "00:02:09", ["E-005"]),
    claim("C-007", "pgregdoc.com", "Three user groups are described: consumers/customers, global administrators, and local administrators; global admins manage countries, subscriptions, notifications/text modules, while local admins manage products/categories.", "00:02:48", ["E-006", "V-001"]),
    claim("C-008", "pgregdoc.com", "The public website remains within support scope because its backend application is supported; the precise frontend ownership boundary is not stated.", "00:04:24", ["E-007"]),
    claim("C-009", "pgregdoc.com", "Admin employees manually add, edit, and delete country-specific safety data sheets and extract documents as PDFs; consumers retrieve available PDFs.", "00:05:07", ["E-008", "V-002"]),
    claim("C-010", "pgregdoc.com", "Application developers use the browser to perform manual application configuration.", "00:05:35", ["E-008"]),
    claim("C-011", "pgregdoc.com", "The application has production and development environments; Azure SQL is described as data storage, Azure Data Factory as processing, and private endpoints/virtual networks as network controls.", "00:05:53", ["E-009", "V-003"]),
    claim("C-012", "pgregdoc.com", "The application reference slide/transcript identifies owner Miguel Angel Moreno-Fernandez, public classification, and low overall BIA.", "00:06:40", ["E-010", "V-003"], confidence="MEDIUM", source_type="TRANSCRIPT+VIDEO_FRAME"),
    claim("C-013", "pgregdoc.com", "The application flow diagram labels PingID as the authentication dependency; IT Access is named for user management. The exact spoken provider phrase remains unclear.", "00:05:41", ["V-002", "E-010"], confidence="MEDIUM", source_type="VIDEO_FRAME+TRANSCRIPT", conflicts=["Transcript exports render the spoken provider phrase differently; frame V-002 visibly labels PingID."]),
    claim("C-014", "pgregdoc.com", "The speaker says the application is not fully developed and starts describing an open-source intention, but the sentence is incomplete.", "00:07:09", ["E-011"], state="SOURCE_UNCERTAIN", confidence="LOW"),
    claim("C-015", "pgregdoc.com", "The technical deep-dive was deferred because the planned presenter said they were not prepared and lacked application/resource access.", "00:08:00", ["E-012", "E-013"]),
    claim("C-016", "North America Central Product Research Testing Panelist Payments", "The application catalogue screen describes a Microsoft-run SaaS/ETL platform for North America CPRT panelist payment data and fulfilment data.", "00:20:51", ["E-020", "V-004"], state="SOURCE_CONFIRMED", confidence="MEDIUM", source_type="VIDEO_FRAME_OCR"),
    claim("C-017", "North America Central Product Research Testing Panelist Payments", "The catalogue description says Salesforce LEX data is exported and loaded to fulfilment vendor servers or a P&G-hosted database.", "00:20:51", ["E-020", "V-004"], state="SOURCE_CONFIRMED", confidence="MEDIUM", source_type="VIDEO_FRAME_OCR"),
    claim("C-018", "North America Central Product Research Testing Panelist Payments", "The catalogue description limits direct database access to PG NA CPRT business, technology development, and operations, with access needed for about five to six people at most.", "00:20:51", ["E-020", "V-004"], state="SOURCE_CONFIRMED", confidence="MEDIUM", source_type="VIDEO_FRAME_OCR"),
    claim("C-019", "North America Central Product Research Testing Panelist Payments", "The catalogue record shows lifecycle status Leverage/Optimize; the speaker says it moved from sunset to leverage optimized while decommissioning remained undecided.", "00:18:23", ["E-021", "E-022", "V-004"], confidence="MEDIUM", source_type="TRANSCRIPT+VIDEO_FRAME"),
    claim("C-020", "North America Central Product Research Testing Panelist Payments", "Limited usage is reported from ticket history, and limited user count is explicitly presented as the speaker's impression.", "00:20:34", ["E-022"], state="SOURCE_UNCERTAIN", confidence="MEDIUM"),
    claim("C-021", "North America Central Product Research Testing Panelist Payments", "Future requests for full decommissioning are expected; the recording does not say decommissioning was approved.", "00:20:38", ["E-022"]),
    claim("C-022", "North America Central Product Research Testing Panelist Payments", "The speaker says code/scripts are stored in a place transcribed as 'data floor'; the proper platform name and location are not verified.", "00:15:20", ["E-017"], state="SOURCE_UNCERTAIN", confidence="LOW"),
    claim("C-023", "North America Central Product Research Testing Panelist Payments", "The presenter reports lacking permission to the application's Azure resource group; another participant advises trying an AMS Admin identity, but successful access is not shown.", "00:12:10", ["E-015", "E-016"]),
    claim("C-024", "North America Central Product Research Testing Panelist Payments", "The planned technical walkthrough was deferred; the presenter lacked preparation and access to resources/code.", "00:15:20", ["E-017", "E-018"]),
    claim("C-025", "North America Central Product Research Testing Panelist Payments", "The phrase 'transition to corruption mining' appears in the transcript during lifecycle discussion and cannot be safely interpreted from the available evidence.", "00:20:51", ["E-023"], state="NEEDS_REVIEW", confidence="LOW"),
]


OPEN_QUESTIONS = {
    "pgregdoc.com": [
        "Which technical owner can provide the deferred architecture walkthrough and source/code ownership?",
        "Where does the mail subscription service run, and what triggers and sends email updates?",
        "Does Azure SQL initiate notifications, or is another service responsible?",
        "Which Azure resources, subscriptions, regions, deployment units, and production/development URLs are in scope?",
        "Which SQL databases/schemas and Data Factory pipelines are used, and what schedules/retries/alerts apply?",
        "Which private endpoints, VNets, DNS, firewall rules, and identity controls apply?",
        "What is the exact identity provider name? The transcript variants conflict ('being'/'spin solutions').",
        "Which IT Access group grants consumer, global-admin, local-admin, and developer permissions?",
        "What is the precise support boundary for the public frontend, backend, and external website?",
        "What are backup, restore, retention, monitoring, incident escalation, and change procedures?",
        "Is the application still under development, and what did the incomplete 'open source' statement mean?",
        "Which version of the app reference/classification/BIA record is current?",
    ],
    "North America Central Product Research Testing Panelist Payments": [
        "What is the verified platform/repository name transcribed as 'data floor', and where are its scripts/code?",
        "Which Azure resource group and approved AMS Admin role are required, and who grants them?",
        "Which Microsoft SaaS/ETL service is used, and what are its environments and operating owner?",
        "Confirm the Salesforce LEX extract, panelist/fulfilment data fields, destinations, schedules, and failure handling shown in the catalogue record.",
        "Confirm which fulfillment vendors and P&G-hosted databases are current destinations.",
        "Who are the application, business, technical, support, and decommissioning decision owners?",
        "What ticket counts, user counts, operational load, and last-use evidence support the lifecycle decision?",
        "Is decommissioning planned, approved, funded, or only a possible future request?",
        "What did 'transition to corruption mining' mean? No interpretation is supported by this recording.",
        "What exact technical session and application-access demonstration were deferred?",
        "Which named individuals should be contacted? The screenshot owner text is too soft to record reliably.",
    ],
}


APP_SECTIONS: dict[str, list[tuple[str, list[str]]]] = {
    "pgregdoc.com": [
        ("Executive Brief", [
            "PG RegDoc is described as a custom backend supporting a public document portal for safety data sheets (SDS) and other non-confidential technical documents. [C-002, C-003]",
            "This session covers its business overview but not the promised technical deep-dive. Treat architecture and access details as a starting evidence set, not an operational runbook. [C-011, C-015]",
        ]),
        ("Business Purpose", [
            "Provide external access to public SDS and technical documents for customers/consumers; subscriptions and email updates are also described. [C-003, C-006]",
            "REACH is mentioned as a related business requirement. The speaker explicitly disclaims familiarity with REACH; the informal 'regulations' gloss is not a verified definition. [C-004, C-005]",
        ]),
        ("Support Scope", [
            "In scope: support for the public website because the team supports the backend application that serves it. [C-008]",
            "Frontend ownership, external site infrastructure, and explicit out-of-scope components are not specified. Do not infer a separate frontend team or exclusion. [C-008]",
        ]),
        ("Users and Roles", [
            "Consumers/customers access public documents and subscribe to notifications. Global administrators manage countries, subscriptions, notifications/text modules; local administrators manage products/categories. [C-006, C-007]",
            "Administrative capabilities depend on the assigned role. [C-007]",
        ]),
        ("Operational Data Flow", [
            "Admin employees manually add, edit, and delete country-specific SDS and extract documents as PDF. Consumers retrieve available SDS PDFs through a browser. Developers use the application for manual configuration. [C-009, C-010]",
            "The transcript does not define the email delivery path or where subscription state is stored. [C-002, C-006]",
        ]),
        ("Technical Architecture", [
            "Evidence names P&G Azure, separate production/development environments, SQL/Azure SQL storage, Azure Data Factory processing, private endpoints, and virtual networks. [C-002, C-011]",
            "The slide shows a technical infrastructure diagram, but component labels and detailed flows are not readable enough to establish specific service instances, topology, deployment pipeline, or network rules. [V-003]",
            "The mail subscription service is named but its implementation and relationship to SQL/Data Factory are unresolved. [C-002]",
        ]),
        ("Access and Authentication", [
            "Public consumer access and role-based administrator access are described; users are said to be managed through IT Access. [C-007, C-013]",
            "The flow diagram labels PingID; transcript exports render the spoken provider phrase differently. Confirm the current identity configuration before operational use. [C-013]",
        ]),
        ("Ownership and Contacts", [
            "The reference overview names Miguel Angel Moreno-Fernandez as owner; this is evidenced in the transcript and slide. [C-012]",
            "A presenter called Muchun was expected to provide technical detail but said they were not prepared and lacked access. This does not establish technical ownership. [C-015]",
        ]),
        ("Application Lifecycle", [
            "No lifecycle status, decommissioning plan, or lifecycle decision is established for PG RegDoc in this recording. [E-009, E-012]",
            "A speaker says the app is not fully developed and begins an 'open source' statement, but the sentence is incomplete and needs clarification. [C-014]",
        ]),
        ("Support Operations", [
            "Recurring evidenced work is manual country-specific SDS maintenance, role-based product/category/country administration, subscription/notification administration, PDF extraction, and manual developer configuration. [C-006, C-007, C-009, C-010]",
            "No monitoring, incident intake, patching cadence, release, restore, or ticket procedures are evidenced. [E-009, E-012]",
        ]),
        ("Troubleshooting Knowledge", [
            "No application symptoms, diagnostic checks, or validated resolutions were demonstrated. The planned technical session was deferred. [C-015]",
            "Do not infer troubleshooting steps from the architecture slide. [V-003]",
        ]),
        ("Procedures / SOP", [
            "No step-by-step support SOP is sufficiently evidenced. The transcript describes business activities, not an approved operational procedure. [C-009, C-010]",
        ]),
        ("Known Risks and Limitations", [
            "The recording is source-incomplete, ending 11m09s before video end; unrecorded technical detail may exist. [E-024]",
            "Technical deep-dive, mail integration, authentication provider, precise website support boundary, and application maturity remain unresolved. [C-008, C-013, C-014, C-015]",
        ]),
        ("Deferred / Missing Knowledge", [
            "Detailed architecture, app components, Azure resource names, SQL model, Data Factory pipelines, private endpoint/VNet routes, monitoring, backup/restore, change/release, identity groups, support escalation, code location, and dependency ownership are missing. [V-003, C-015]",
        ]),
        ("Open Questions", OPEN_QUESTIONS["pgregdoc.com"]),
        ("Action Items / Follow-ups", [
            "Schedule the deferred technical walkthrough with the application technical owner; confirm the presenter has approved access before the session. [C-015]",
            "Validate mail/notification implementation, authentication provider, IT Access groups, support boundary, and current classification/BIA record. [C-002, C-012, C-013]",
        ]),
        ("Ambiguities / Needs Review", [
            "REACH definition is explicitly uncertain; preserve that as speaker uncertainty. [C-005]",
            "Resolve the authentication phrase conflict and the incomplete development/open-source statement. [C-013, C-014]",
        ]),
        ("Glossary", [
            "SDS: safety data sheet. [C-003, C-009]",
            "Azure Data Factory: named in the source as supporting data processing. [C-011]",
            "Production and development: the two environments named in the source. [C-011]",
            "REACH is excluded as an unverified definition; the flow diagram labels PingID, while the spoken provider phrase remains ambiguous. [C-005, C-013]",
        ]),
    ],
    "North America Central Product Research Testing Panelist Payments": [
        ("Executive Brief", [
            "Session 41 provides limited business/lifecycle context and a captured application-catalogue description. It does not provide the promised technical walkthrough. [C-016, C-019, C-024]",
            "The catalogue screen suggests an ETL path for panelist-payment and fulfilment data; validate the source and destinations with the technical owner before operating it. [C-016, C-017]",
        ]),
        ("Business Purpose", [
            "The application is named North America Central Product Research Testing Panelist Payments. Its record describes panelist data and fulfilment data being transferred, and Salesforce LEX exports loaded to fulfilment vendor servers or a P&G-hosted database. These details are from the captured catalogue screen, not a completed technical walkthrough. [C-001, C-016, C-017]",
        ]),
        ("Support Scope", [
            "The catalogue lists P&G AMS Support Team; it describes direct database access for PG NA CPRT business, technology development, and operations, with about five to six people at most. [C-018]",
            "Support boundary across SaaS provider, ETL, vendor servers, and P&G-hosted database is not fully established. [C-016, C-017]",
        ]),
        ("Users and Roles", [
            "The catalogue description identifies PG NA CPRT business, technology development, and operations as direct database users; access expected for five to six people at most. [C-018]",
            "The recording does not name individual approvers or provide a role matrix. [C-018]",
        ]),
        ("Operational Data Flow", [
            "Captured record: Salesforce LEX data is exported and loaded to fulfilment vendor servers or a P&G-hosted database; panelist and fulfilment data are transferred using the application. [C-016, C-017]",
            "No file formats, schedules, validation rules, retry/error paths, reconciliation, or manual operation steps are described. [C-017]",
        ]),
        ("Technical Architecture", [
            "The captured catalogue description calls this a Microsoft-run cloud/SaaS platform using ETL. No specific Microsoft service, Azure subscription/resource, environment, network boundary, database engine, or integration implementation is confirmed. [C-016, C-017]",
            "The speaker says code/scripts are stored in a location transcribed as 'data floor'; its exact name and URL/repository are unverified. [C-022]",
        ]),
        ("Access and Authentication", [
            "A presenter reports lacking permission to the Azure resource group. A participant says to try an AMS Admin identity; the recording does not show whether that worked. [C-023]",
            "The catalogue says direct database access is limited to named business/technology/operations functions and approximately five to six people. No credential or identity provider is stated. [C-018]",
        ]),
        ("Ownership and Contacts", [
            "P&G AMS Support Team appears in the catalogue screenshot. The individual owner field is too soft to transcribe reliably and is omitted. Business and technical owners are not confirmed. [C-018, V-004]",
        ]),
        ("Application Lifecycle", [
            "The speaker reports a move from sunset to leverage optimized because decommissioning had not been decided. The captured record displays Leverage/Optimize. [C-019]",
            "Limited usage is based on ticket history; limited users are described as the speaker's impression. Possible future decommissioning is expected, not approved. [C-020, C-021]",
        ]),
        ("Support Operations", [
            "The application is associated with limited ticket usage and possible future decommission requests. The recording gives no ticket queue, on-call model, monitoring, reconciliation, support schedule, or recurring operator checklist. [C-020, C-021]",
        ]),
        ("Troubleshooting Knowledge", [
            "Observed access issue: presenter lacked Azure resource-group permission. The suggested AMS Admin identity was not shown to resolve it. No validated resolution path is available. [C-023]",
        ]),
        ("Procedures / SOP", [
            "No operational procedure is supported. Do not turn the access attempt or unverified ETL description into runbook steps. [C-017, C-023, C-024]",
        ]),
        ("Known Risks and Limitations", [
            "Lifecycle decision remains undecided; low usage/user claims are partly impression-based; source ends before the video; the ETL description is only a captured catalogue record. [C-019, C-020, E-024]",
            "The phrase 'transition to corruption mining' is suspicious and unresolved. Do not publish it as a lifecycle activity. [C-025]",
        ]),
        ("Deferred / Missing Knowledge", [
            "Verified service/repository name, code location, access group, actual architecture, ETL jobs, source/target schemas, vendor list, monitoring, failure handling, ownership, ticket statistics, lifecycle decision, and technical walkthrough are missing. [C-022, C-023, C-024]",
        ]),
        ("Open Questions", OPEN_QUESTIONS["North America Central Product Research Testing Panelist Payments"]),
        ("Action Items / Follow-ups", [
            "Schedule the deferred technical walkthrough; arrange approved resource-group access and confirm the correct AMS Admin role through the normal access process. [C-023, C-024]",
            "Locate and verify the code/scripts repository, dataflows, destinations, ticket/user evidence, and lifecycle decision owner. [C-017, C-020, C-021, C-022]",
            "Ask the speaker to clarify 'transition to corruption mining'; do not guess its meaning. [C-025]",
        ]),
        ("Ambiguities / Needs Review", [
            "'Data floor' could not be verified as a platform/repository name. No interpretation is supported. [C-022]",
            "'Transition to corruption mining' has no supported interpretation in the source. [C-025]",
        ]),
        ("Glossary", [
            "ETL: Extract, Transform, Load; this expansion appears in the captured application-catalogue description. [C-016]",
            "SaaS: software as a service; this expansion appears in the captured application-catalogue description. [C-016]",
            "'Data floor' is not included as a verified glossary term. [C-022]",
        ]),
    ],
}


TIMELINE = [
    ("E-001", "00:00:47", "00:01:17", "SESSION", "Opening identifies two applications and names the North America application.", ["C-001"], ["TRANSCRIPT"]),
    ("E-002", "00:01:26", "00:01:47", "pgregdoc.com", "PG RegDoc custom backend, P&G Azure (slide), SQL and mail subscription service.", ["C-002"], ["TRANSCRIPT", "V-001"]),
    ("E-003", "00:01:47", "00:02:09", "pgregdoc.com", "Public SDS/technical documents and REACH reference; speaker disclaims REACH familiarity.", ["C-003", "C-004", "C-005"], ["TRANSCRIPT"]),
    ("E-005", "00:02:09", "00:03:25", "pgregdoc.com", "Subscriptions, notifications, admin functions, and role descriptions.", ["C-006", "C-007"], ["TRANSCRIPT", "V-001"]),
    ("E-007", "00:04:24", "00:04:38", "pgregdoc.com", "Question and response establish public website support via backend; frontend boundary remains unclear.", ["C-008"], ["TRANSCRIPT"]),
    ("E-008", "00:05:07", "00:05:41", "pgregdoc.com", "Manual SDS maintenance/PDF retrieval and developer configuration; data-flow slide.", ["C-009", "C-010"], ["TRANSCRIPT", "V-002"]),
    ("E-009", "00:05:53", "00:06:40", "pgregdoc.com", "Production/development, Azure SQL, Data Factory, private endpoints and virtual networks.", ["C-011"], ["TRANSCRIPT", "V-003"]),
    ("E-010", "00:06:40", "00:07:09", "pgregdoc.com", "Owner/classification/BIA; authentication term uncertain and IT Access named.", ["C-012", "C-013"], ["TRANSCRIPT", "V-003"]),
    ("E-011", "00:07:09", "00:07:56", "pgregdoc.com", "Incomplete application maturity/open-source statement.", ["C-014"], ["TRANSCRIPT"]),
    ("E-012", "00:08:00", "00:09:50", "pgregdoc.com", "Technical presentation deferred; presenter says not prepared and lacks access.", ["C-015"], ["TRANSCRIPT"]),
    ("E-015", "00:11:53", "00:12:45", "North America Central Product Research Testing Panelist Payments", "Presenter reports no resource-group permission.", ["C-023"], ["TRANSCRIPT"]),
    ("E-016", "00:12:46", "00:13:18", "North America Central Product Research Testing Panelist Payments", "Participant advises trying AMS Admin identity; result not shown.", ["C-023"], ["TRANSCRIPT"]),
    ("E-017", "00:15:00", "00:16:20", "North America Central Product Research Testing Panelist Payments", "Data floor/code/scripts, access problem, and no prepared slides.", ["C-022", "C-024"], ["TRANSCRIPT"]),
    ("E-018", "00:16:42", "00:18:40", "North America Central Product Research Testing Panelist Payments", "Attempt to switch to AMS Admin account/retrieve access; 74.78-second speech gap occurs in this interval.", ["C-023"], ["TRANSCRIPT"]),
    ("E-020", "00:20:51", "00:20:51", "North America Central Product Research Testing Panelist Payments", "Application catalogue screenshot shows app description, lifecycle, access context, and support group.", ["C-016", "C-017", "C-018", "C-019"], ["VIDEO_FRAME_OCR", "V-004"]),
    ("E-021", "00:18:23", "00:20:34", "North America Central Product Research Testing Panelist Payments", "Sunset to leverage optimized; decommissioning undecided.", ["C-019"], ["TRANSCRIPT"]),
    ("E-022", "00:20:34", "00:20:50", "North America Central Product Research Testing Panelist Payments", "Limited tickets/use impression and future decommission request expectation.", ["C-020", "C-021"], ["TRANSCRIPT"]),
    ("E-023", "00:20:50", "00:20:56", "North America Central Product Research Testing Panelist Payments", "Suspicious phrase 'transition to corruption mining'.", ["C-025"], ["TRANSCRIPT"]),
    ("E-024", "00:23:55.890", "00:35:05.367", "SESSION", "No transcript segment reaches this final 669.477-second video interval; later sampled frames show gallery only.", [], ["SOURCE_COVERAGE", "VIDEO_FRAME"]),
]


REVIEW_ITEMS = [
    {"id": "RQ-001", "type": "SOURCE_UNCERTAIN", "application": "pgregdoc.com", "ambiguity": "REACH was glossed as 'regulations' by a speaker who said they were not familiar with it.", "timestamp": "00:01:49", "raw_transcript": "I'm not quite familiar with REACH, but when I tried to search within PNG documentation, this simply means regulations.", "reason": "Speaker explicitly disclaims familiarity; do not convert the gloss into a canonical definition.", "possible_interpretation": None, "needs_human_review": True, "evidence_refs": ["C-005"]},
    {"id": "RQ-002", "type": "TRANSCRIPT_CONFLICT", "application": "pgregdoc.com", "ambiguity": "Transcript exports render the spoken authentication provider phrase differently (being solutions/spin solutions); flow diagram V-002 labels PingID.", "timestamp": "00:06:55", "raw_transcript": "Authentication being used as spin solutions and users are ...", "reason": "Visual evidence labels PingID, but confirm current identity configuration and the spoken-term discrepancy before operational use.", "possible_interpretation": "PingID is the provider shown in the sampled application flow diagram.", "needs_human_review": True, "evidence_refs": ["C-013", "V-002"]},
    {"id": "RQ-003", "type": "SEMANTIC_ANOMALY", "application": "North America Central Product Research Testing Panelist Payments", "ambiguity": "transition to corruption mining", "timestamp": "00:20:51", "raw_transcript": "But since this is in leverage optimized lifecycle status, we will be proceeding with the transition to corruption mining.", "reason": "Phrase is semantically suspicious in a lifecycle discussion and unsupported by other evidence.", "possible_interpretation": None, "needs_human_review": True, "evidence_refs": ["C-025"]},
    {"id": "RQ-004", "type": "SOURCE_UNCERTAIN", "application": "North America Central Product Research Testing Panelist Payments", "ambiguity": "data floor", "timestamp": "00:15:31", "raw_transcript": "Something like a date floor. So all the codes, I mean, all the scripts are coded in the, I mean, the floor.", "reason": "Transcript variants and surrounding context do not verify the platform/repository name.", "possible_interpretation": None, "needs_human_review": True, "evidence_refs": ["C-022"]},
    {"id": "RQ-005", "type": "INCOMPLETE_STATEMENT", "application": "pgregdoc.com", "ambiguity": "Application maturity and 'open source' intent.", "timestamp": "00:07:09", "raw_transcript": "I think the only thing missing is the fact that the application is not fully developed. So we are trying to keep this as an open source, but in the end, the application will...", "reason": "Sentence trails off; current development state and intent cannot be safely inferred.", "possible_interpretation": None, "needs_human_review": True, "evidence_refs": ["C-014"]},
    {"id": "RQ-006", "type": "UNEXPLAINED_COVERAGE_GAP", "application": "SESSION", "ambiguity": "Transcript missing from 00:23:55.890 to 00:35:05.367.", "timestamp": "00:23:55.890-00:35:05.367", "raw_transcript": "No transcript segments available in this interval.", "reason": "The 669.477-second gap includes most of the meeting tail; visual samples after 00:24:39 show gallery, not application evidence.", "possible_interpretation": None, "needs_human_review": True, "evidence_refs": ["E-024"]},
    {"id": "RQ-007", "type": "INTERNAL_SPEECH_GAP", "application": "North America Central Product Research Testing Panelist Payments", "ambiguity": "74.78 seconds without transcript after 'Give me a few minutes' while switching/retrieving access.", "timestamp": "00:17:00.550-00:18:15.330", "raw_transcript": "The prior segment says 'Give me a few minutes'; the next available segment is 'I think I should retrieve the new password from...'.", "reason": "Context suggests an access pause but the content of the gap is not recorded in transcript.", "possible_interpretation": "A pause while attempting access is supported by the adjacent statements; no technical facts can be inferred.", "needs_human_review": True, "evidence_refs": ["E-018"]},
    {"id": "RQ-008", "type": "VISUAL_OCR_REVIEW", "application": "North America Central Product Research Testing Panelist Payments", "ambiguity": "Some ServiceNow-style catalogue text is small/soft in the sampled screen.", "timestamp": "00:20:51.840", "raw_transcript": "Frame V-004 contains a catalogue description; exact app ID and named owner are not legible enough to report.", "reason": "The app purpose/lifecycle phrases are readable, but exact owner and identifier remain unclear.", "possible_interpretation": None, "needs_human_review": True, "evidence_refs": ["V-004"]},
]


GATE_EVALUATIONS = {
    "SOURCE_COVERAGE": {"status": "FAIL", "evidence": "Transcript reaches only 68.2% of video duration; final gap is 669.477 seconds."},
    "CLAIM_GROUNDING": {"status": "PARTIAL", "evidence": "All claims have source fields and refs; source-uncertain claims remain flagged; no external facts used."},
    "AMBIGUITY_HANDLING": {"status": "PASS", "evidence": "Eight items are isolated in review-queue; unsupported interpretations are null."},
    "APP_SEGMENTATION": {"status": "PASS", "evidence": "PG RegDoc and North America application have distinct mission packs and claim sets."},
    "SUPPORT_SCOPE": {"status": "PARTIAL", "evidence": "PG public-site/backend support stated; exact frontend boundary and North America vendor boundary remain open."},
    "DATA_FLOW": {"status": "PARTIAL", "evidence": "PG manual document flow and North America catalogue ETL summary exist; schedules/error paths are missing."},
    "ARCHITECTURE": {"status": "PARTIAL", "evidence": "Named PG Azure components are grounded; detailed diagram labels and North America service topology are unverified."},
    "ACCESS_AUTH": {"status": "PARTIAL", "evidence": "Roles and access issue documented; provider term conflicts; approved grants and identity config unknown."},
    "OWNERSHIP": {"status": "PARTIAL", "evidence": "PG business owner recorded; technical/support contacts for both apps incomplete."},
    "OPERATIONS": {"status": "PARTIAL", "evidence": "Recurring PG admin tasks known; monitoring/incident/change routines absent; North America operations incomplete."},
    "RISKS": {"status": "PARTIAL", "evidence": "Source gap, access/lifecycle uncertainty, unsupported architecture details and anomaly identified."},
    "OPEN_QUESTIONS": {"status": "PASS", "evidence": "Application-specific questions listed for missing technical, support, access, ownership and lifecycle information."},
    "FOLLOW_UPS": {"status": "PASS", "evidence": "Deferred technical walkthroughs and targeted validation tasks recorded."},
    "EVIDENCE_TIMELINE": {"status": "PASS", "evidence": "Timestamped evidence events link claims to transcript/frame sources."},
    "SOURCE_MAPPING": {"status": "PASS", "evidence": "Transcript exports, video hash, frame map and selected frames are listed."},
}


def stamp(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    millis = int(round((seconds - whole) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def read_source() -> dict[str, Any]:
    video_info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(SOURCE_VIDEO)
    ], text=True))["format"]
    duration = float(video_info["duration"])
    primary = json.loads(PRIMARY_SEGMENTS.read_text(encoding="utf-8"))
    variant = json.loads(TRANSCRIPT_VARIANT.read_text(encoding="utf-8"))
    mapping = json.loads((FRAMES_ROOT / "frame_mapping.json").read_text(encoding="utf-8"))
    first_end = max(primary["segments"][-1]["end"], variant["segments"][-1]["end"])
    segments = variant["segments"]
    segments_for_coverage = segments if segments[-1]["end"] == first_end else primary["segments"]
    coverage = measure_source_coverage(
        duration,
        segments_for_coverage,
        [item["timestamp"] for item in mapping["frames"]],
    )
    coverage["transcript_last_timestamp_seconds"] = first_end
    coverage["transcript_last_timestamp_coverage_percent"] = round(100 * first_end / duration, 2)
    coverage["trailing_gap_seconds"] = round(duration - first_end, 3)
    coverage["unexplained_gaps"][-2]["start"] = first_end
    coverage["unexplained_gaps"][-2]["seconds"] = duration - first_end
    h = hashlib.sha256()
    with SOURCE_VIDEO.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    coverage.update({
        "video_filename": SOURCE_VIDEO.name,
        "video_sha256": h.hexdigest(),
        "duration_formatted": stamp(duration),
        "transcript_last_timestamp_formatted": stamp(first_end),
        "trailing_gap_formatted": stamp(duration - first_end),
        "transcript_variants": [PRIMARY_SEGMENTS.name, TRANSCRIPT_VARIANT.name],
        "transcript_variant_last_timestamps": [primary["segments"][-1]["end"], variant["segments"][-1]["end"]],
        "visual_sampling_interval_seconds": 56.902,
        "visual_frame_count_after_transcript_end": sum(1 for f in mapping["frames"] if f["timestamp"] > first_end),
        "visual_post_transcript_review": "Sampled frames after transcript end show meeting gallery only; no legible application evidence.",
    })
    return {"duration": duration, "segments": segments, "mapping": mapping, "coverage": coverage}


def prepare_assets(mapping: dict[str, Any]) -> dict[str, Path]:
    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    specs = {
        "V-001": (0, (390, 225, 1110, 660), "pgregdoc-overview.png"),
        "V-002": (5, (390, 225, 1110, 660), "pgregdoc-data-flow.png"),
        "V-003": (6, (390, 225, 1110, 790), "pgregdoc-technical-architecture.png"),
        "V-004": (21, (390, 530, 1130, 655), "north-america-catalogue-description.png"),
        "V-005": (21, (390, 370, 760, 405), "north-america-lifecycle-status.png"),
    }
    result: dict[str, Path] = {}
    for evidence_id, (number, box, filename) in specs.items():
        image = Image.open(FRAMES_ROOT / f"frame_{number:04}.png")
        crop = image.crop(box)
        crop.save(assets / filename, optimize=True)
        result[evidence_id] = assets / filename
    return result


def app_claims(app_id: str) -> list[dict[str, Any]]:
    return [item for item in CLAIMS if item["application"] == app_id]


def app_knowledge(app_id: str) -> dict[str, Any]:
    facts = []
    for item in app_claims(app_id):
        confirmed = item["verification_state"] in {"SOURCE_CONFIRMED", "EXTERNAL_VERIFIED"}
        facts.append({
            "fact_key": item["id"],
            "fact": item["claim"],
            "first_seen": {"session_id": SESSION_ID, "timestamp": item["source_timestamp"]},
            "last_confirmed": {"session_id": SESSION_ID, "timestamp": item["source_timestamp"]} if confirmed else None,
            "supporting_sessions": [SESSION_ID],
            "confidence": item["confidence"],
            "verification_state": item["verification_state"],
            "conflicts": item["conflicts"],
            "evidence_refs": item["evidence_refs"],
        })
    # The duplicate-named transcript is a second ASR export of the same SHA-256 video, not another session.
    facts = merge_application_facts([], facts)
    return {
        "schema_version": "app-knowledge-v1",
        "knowledge_level": "APPLICATION_MISSION_PACK",
        "version": 1,
        "application": app_id,
        "source_coverage_status": "SOURCE_INCOMPLETE",
        "cross_session_status": "BASELINE_SINGLE_SESSION",
        "prior_sessions_found": [],
        "source_sessions": [SESSION_ID],
        "external_verified_facts": 0,
        "facts": facts,
        "conflicts": [fact for fact in facts if fact["verification_state"] == "CONFLICTING" or fact["conflicts"]],
    }


def make_source_map(source: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = source["mapping"]
    frame_by_id = {
        "V-001": 0,
        "V-002": 5,
        "V-003": 6,
        "V-004": 21,
        "V-005": 21,
    }
    selected = []
    for evidence_id, num in frame_by_id.items():
        row = mapping["frames"][num]
        selected.append({
            "evidence_id": evidence_id,
            "source_type": "VIDEO_FRAME",
            "timestamp_seconds": row["timestamp"],
            "timestamp": row["timestamp_formatted"],
            "source_path": str((FRAMES_ROOT / row["frame_file"]).relative_to(ROOT)),
            "derived_asset": f"assets/{Path(prepare_assets_cache[evidence_id]).name}",
            "sha256": hashlib.sha256((FRAMES_ROOT / row["frame_file"]).read_bytes()).hexdigest(),
        })
    return [
        {"source_id": "S-VIDEO", "source_type": "VIDEO", "path": str(SOURCE_VIDEO.relative_to(ROOT)),
         "sha256": source["coverage"]["video_sha256"], "duration_seconds": source["duration"]},
        {"source_id": "S-TRANSCRIPT-PRIMARY", "source_type": "TRANSCRIPT_SEGMENTS", "path": str(PRIMARY_SEGMENTS.relative_to(ROOT)),
         "sha256": hashlib.sha256(PRIMARY_SEGMENTS.read_bytes()).hexdigest(), "segments": 172,
         "last_timestamp_seconds": source["coverage"]["transcript_variant_last_timestamps"][0]},
        {"source_id": "S-TRANSCRIPT-SECONDARY", "source_type": "TRANSCRIPT_SEGMENTS", "path": str(TRANSCRIPT_VARIANT.relative_to(ROOT)),
         "sha256": hashlib.sha256(TRANSCRIPT_VARIANT.read_bytes()).hexdigest(), "segments": 131,
         "last_timestamp_seconds": source["coverage"]["transcript_variant_last_timestamps"][1]},
        {"source_id": "S-FRAME-MAP", "source_type": "FRAME_MAPPING", "path": str((FRAMES_ROOT / "frame_mapping.json").relative_to(ROOT)),
         "sha256": hashlib.sha256((FRAMES_ROOT / "frame_mapping.json").read_bytes()).hexdigest(),
         "frames": 36, "sampling_method": source["mapping"]["video_info"]["extraction_method"]},
        *selected,
    ]


def markdown_for_app(app_id: str, sections: list[tuple[str, list[str]]], assets: dict[str, Path], *, app_pack: bool = False) -> str:
    lines = [f"# Application Mission Pack - {app_id}", "", "- **Version:** 1",
             f"- **Knowledge state:** PARTIAL - source session {SESSION_ID}; source coverage is incomplete",
             "- **Provenance:** Session 41 only. No other source session for this application was found in the local transcription/document corpus. Duplicate transcript exports share one source-video hash and count as one session.", ""]
    if app_id == "pgregdoc.com":
        visual_order = ["V-001", "V-002", "V-003"]
    else:
        visual_order = ["V-004"]
    for title, body in sections:
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {item}" for item in body)
        if title == "Operational Data Flow" and "V-002" in visual_order:
            lines.extend(["", f"![Source data-flow slide at 00:05:41](../../../assets/{assets['V-002'].name})"])
        if title == "Technical Architecture" and "V-003" in visual_order:
            lines.extend(["", f"![Source technical-architecture slide at 00:06:38](../../../assets/{assets['V-003'].name})"])
        if title == "Business Purpose" and "V-001" in visual_order:
            lines.extend(["", f"![Source application overview slide at 00:00:56](../../../assets/{assets['V-001'].name})"])
        if title == "Business Purpose" and "V-004" in visual_order:
            lines.extend(["", f"![Captured application catalogue description at 00:20:51](../../../assets/{assets['V-004'].name})"])
        if title == "Application Lifecycle" and "V-004" in visual_order:
            lines.extend(["", f"![Captured lifecycle status at 00:20:51](../../../assets/{assets['V-005'].name})"])
        lines.append("")
    lines.extend(["## Evidence Timeline", "", "See the session-level `evidence-timeline.json`; application evidence IDs are listed below.", ""])
    lines.extend(f"- `{item['id']}` {item['source_timestamp']} - {item['claim']}" for item in app_claims(app_id))
    lines.extend(["", "## Source Map", "", "See the session-level source map in `evidence-timeline.json`; evidence references are limited to Session 41 source media, transcript segments and sampled video frames.", ""])
    return "\n".join(lines)


def markdown_for_session(source: dict[str, Any], gates: dict[str, Any], app_docs: dict[str, str], source_map: list[dict[str, Any]], assets: dict[str, Path]) -> str:
    cov = source["coverage"]
    lines = [
        "# Session 41 - AMS / Application Support Mission Pack",
        "",
        "- **Artifact version:** 3",
        "- **Source status:** SOURCE_INCOMPLETE",
        "**Quality gate:** FAIL - not fully grounded; technical claims beyond the covered source are deferred.",
        "",
        "## Source Coverage",
        "",
        f"- Video duration: {cov['duration_formatted']} ({cov['video_duration_seconds']:.3f} seconds).",
        f"- Transcript last timestamp: {cov['transcript_last_timestamp_formatted']} ({cov['transcript_last_timestamp_seconds']:.3f} seconds).",
        f"- Transcript coverage by end timestamp: {cov['transcript_last_timestamp_coverage_percent']:.2f}%; temporal span from first segment: {cov['transcript_span_coverage_percent']:.2f}%.",
        f"- Leading gap: {stamp(cov['leading_gap_seconds'])}; trailing gap: {cov['trailing_gap_formatted']} ({cov['trailing_gap_seconds']:.3f} seconds).",
        f"- Internal speech gap: 00:17:00.550-00:18:15.330 (74.780 seconds), during an access/account switch; its content is unavailable in the transcript.",
        f"- Visual evidence: {cov['visual_frame_count']} sampled frames, approximately 56.9 seconds apart; first-to-last sampled span is {cov['visual_sampled_span_percent']:.2f}% of the video, not continuous visual coverage. {cov['visual_frame_count_after_transcript_end']} frames after transcript end show the meeting gallery only.",
        "- The final 11m09s gap is unexplained by the transcript and sampled frames; no content is inferred for it.",
        "",
        "## Quality Gate",
        "",
        "| Gate | Result | Evidence |",
        "|---|---|---|",
    ]
    for name, result in gates["gates"].items():
        lines.append(f"| {name} | {result['status']} | {result['evidence']} |")
    lines.extend(["", "## Applications Identified", "", "This recording is segmented into two independent application packs. Neither is promoted to FULLY_GROUNDED while source coverage is incomplete.", ""])
    for app_id, app_doc in app_docs.items():
        rel = "apps/" + APP_IDS[app_id] + "/v000001/APP_MISSION_PACK.md"
        lines.extend([f"### {app_id}", "", f"[Open application mission pack]({rel})", ""])
    lines.extend([
        "## Cross-session Knowledge",
        "",
        "The available local corpus search found no prior Session 41-independent source for either application. The two same-video transcript exports are alternative ASR outputs, not separate supporting sessions. Application packs therefore form single-session baselines; repeated facts are deduplicated within each pack and preserve provenance.",
        "",
        "## Evidence Timeline",
        "",
    ])
    for eid, start, end, app, summary, ids, types in TIMELINE:
        lines.append(f"- **{start}-{end} | {app} | {eid}:** {summary} {' '.join(f'[{c}]' for c in ids)}".rstrip())
    lines.extend(["", "## Source Map", ""])
    for item in source_map:
        lines.append(f"- `{item['evidence_id'] if 'evidence_id' in item else item['source_id']}`: `{item.get('path', item.get('source_path'))}` ({item.get('source_type')}; sha256 `{item.get('sha256', '')}`).")
    lines.extend(["", "## Review Queue", "", "See `review-queue.json`; ambiguous phrases remain isolated and have no unsupported expansions.", ""])
    return "\n".join(lines)


def pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("MissionTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=21, leading=26, textColor=colors.HexColor("#123047"), spaceAfter=10*mm, alignment=TA_LEFT),
        "heading": ParagraphStyle("MissionHeading", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#12566D"), spaceBefore=5*mm, spaceAfter=2*mm, keepWithNext=True),
        "body": ParagraphStyle("MissionBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=2.2*mm),
        "small": ParagraphStyle("MissionSmall", parent=base["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#465563"), spaceAfter=1.5*mm),
    }


def render_pdf(path: Path, title: str, subtitle: str, sections: list[tuple[str, list[str]]], *, image_paths: dict[str, Path] | None = None) -> None:
    from xml.sax.saxutils import escape

    styles = pdf_styles()
    story: list[Any] = [Paragraph(escape(title), styles["title"]), Paragraph(escape(subtitle), styles["body"]), Spacer(1, 3*mm)]
    banner = Table([[Paragraph("SOURCE_INCOMPLETE - do not treat this package as a fully grounded support manual", styles["body"])]], colWidths=[174*mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1),colors.HexColor("#FFF2D8")),("BOX",(0,0),(-1,-1),0.8,colors.HexColor("#BE7B00")),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story.extend([banner, Spacer(1, 4*mm)])
    image_map = image_paths or {}
    active_application = title
    for heading, paragraphs in sections:
        if heading.startswith("Application: "):
            active_application = heading.removeprefix("Application: ")
        story.append(Paragraph(escape(heading), styles["heading"]))
        for paragraph in paragraphs:
            story.append(Paragraph(escape(paragraph), styles["body"]))
        key = heading.lower()
        selected = []
        pg_app = "pgregdoc.com" in active_application
        na_app = "North America Central Product Research Testing Panelist Payments" in active_application
        if "operational data flow" in key and pg_app and "V-002" in image_map:
            selected.append("V-002")
        if "technical architecture" in key and pg_app and "V-003" in image_map:
            selected.append("V-003")
        if heading == "Business Purpose" and pg_app and "V-001" in image_map:
            selected.append("V-001")
        if heading == "Application Catalogue Evidence" and na_app and "V-004" in image_map:
            selected.append("V-004")
        if "application lifecycle" in key and na_app and "V-005" in image_map:
            selected.append("V-005")
        for eid in selected:
            image = image_map[eid]
            with Image.open(image) as opened:
                width, height = opened.size
            scale = min(168*mm/width, 86*mm/height, 1.0)
            story.extend([Spacer(1, 2*mm), PDFImage(str(image), width=width*scale, height=height*scale), Paragraph(f"Source frame {eid}; exact timestamp in evidence-timeline.json.", styles["small"])])
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=17*mm, title=title, author="Zo Media Intelligence")
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#52616B"))
        canvas.drawString(18*mm, 10*mm, "Session 41 Mission Pack - v3 - SOURCE_INCOMPLETE")
        canvas.drawRightString(A4[0]-18*mm, 10*mm, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    if not SOURCE_VIDEO.is_file() or not PRIMARY_SEGMENTS.is_file() or not FRAMES_ROOT.is_dir():
        raise FileNotFoundError("Session 41 source video, transcript, or frame mapping is missing.")
    OUT.mkdir(parents=True, exist_ok=True)
    source = read_source()
    assets = prepare_assets(source["mapping"])
    global prepare_assets_cache
    prepare_assets_cache = assets
    source_map = make_source_map(source)
    if errors := validate_claim_records(CLAIMS):
        raise ValueError("Invalid claim data: " + "; ".join(errors))
    gates = evaluate_quality_gates(GATE_EVALUATIONS, source["coverage"])
    if gates["fully_grounded"]:
        raise AssertionError("Coverage gate incorrectly allowed this source to pass fully grounded.")

    app_packs: dict[str, dict[str, Any]] = {}
    app_markdown: dict[str, str] = {}
    for app_id, sections in APP_SECTIONS.items():
        app_root = OUT / "apps" / APP_IDS[app_id] / "v000001"
        app_root.mkdir(parents=True, exist_ok=True)
        app_doc = markdown_for_app(app_id, sections, assets)
        (app_root / "APP_MISSION_PACK.md").write_text(app_doc, encoding="utf-8")
        data = app_knowledge(app_id)
        (app_root / "app-knowledge.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        pdf_sections = list(sections)
        if app_id != "pgregdoc.com":
            pdf_sections.insert(1, ("Application Catalogue Evidence", ["Source frame V-004; OCR and visual review support the limited catalogue details included above. Exact owner and application ID are intentionally omitted because they are not legible enough."]))
        render_pdf(app_root / "APP_MISSION_PACK.pdf", f"Application Mission Pack - {app_id}", "Operational support knowledge | version 1 | evidence-limited baseline", pdf_sections, image_paths=assets)
        app_packs[app_id] = data
        app_markdown[app_id] = app_doc

    coverage = source["coverage"]
    knowledge = {
        "schemaVersion": 2,
        "qualitySchemaVersion": "mission-pack-v1",
        "documentId": "session-41-mission-pack-v3",
        "source": SESSION_ID + ".mp4",
        "documentationMode": "AMS_SUPPORT_MISSION_PACK",
        "title": "Session 41 - AMS / Application Support Mission Pack",
        "executiveSummary": "Two applications were discussed. PG RegDoc has business, role, document-flow and high-level Azure evidence; the technical deep-dive was deferred. North America has lifecycle context and a captured catalogue description, but no completed technical walkthrough. A 669.477-second transcript gap prevents FULLY_GROUNDED status.",
        "sourceCoverage": coverage,
        "qualityGate": gates,
        "applications": [app_packs[app] for app in APP_SECTIONS],
        "claims": CLAIMS,
        "sections": [],
        "procedures": [],
        "glossary": [],
        "reviewStatus": "SOURCE_INCOMPLETE",
        "fullyGrounded": False,
        "externalVerifiedFacts": 0,
        "generation": {"method": "CURATED_FROM_SOURCE", "external_synthesis_used": False, "source_video_sha256": coverage["video_sha256"]},
    }
    for app_id, sections in APP_SECTIONS.items():
        for index, (title, body) in enumerate(sections, start=1):
            refs = sorted({ref for cl in app_claims(app_id) for ref in cl["evidence_refs"] if any(ref in line for line in body)})
            section_claims = [cl for cl in app_claims(app_id) if any(cl["id"] in line for line in body)]
            knowledge["sections"].append({
                "id": f"{APP_IDS[app_id]}-s{index:02d}",
                "sectionType": title.upper().replace(" / ", "_").replace(" ", "_"),
                "title": f"{app_id} - {title}",
                "summary": " ".join(body),
                "claims": section_claims,
                "evidenceRefs": refs,
                "summaryEvidenceRefs": refs,
                "screenshotCandidates": [eid for eid in ("V-001", "V-002", "V-003", "V-004") if eid in refs],
                "order": index,
            })
    (OUT / "knowledge-document.json").write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "evidence-timeline.json").write_text(json.dumps({
        "schema_version": "evidence-timeline-v1",
        "source_coverage": coverage,
        "events": [{"id": eid, "start": start, "end": end, "application": app, "summary": summary, "claim_ids": ids, "source_types": types} for eid, start, end, app, summary, ids, types in TIMELINE],
        "source_map": source_map,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "review-queue.json").write_text(json.dumps({"schema_version": "review-queue-v1", "items": REVIEW_ITEMS}, indent=2, ensure_ascii=False), encoding="utf-8")
    quality_report = {
        "OLD_SECTION_COUNT": 11,
        "NEW_SECTION_COUNT": 52,
        "SESSION_SECTION_COUNT": 10,
        "APPLICATION_SECTION_HEADINGS_PER_PACK": 21,
        "APPLICATION_OPERATIONAL_SECTIONS_PER_PACK": 18,
        "VIDEO_DURATION": coverage["duration_formatted"],
        "TRANSCRIPT_COVERAGE": f"{coverage['transcript_last_timestamp_coverage_percent']:.2f}% by end timestamp; {coverage['transcript_span_coverage_percent']:.2f}% from first transcript timestamp",
        "COVERAGE_GAP": coverage["trailing_gap_formatted"],
        "GROUNDED_CLAIMS": sum(c["verification_state"] in {"SOURCE_CONFIRMED", "EXTERNAL_VERIFIED"} for c in CLAIMS),
        "UNCERTAIN_CLAIMS": sum(c["verification_state"] == "SOURCE_UNCERTAIN" for c in CLAIMS),
        "CLAIMS_NEEDS_REVIEW": sum(c["verification_state"] in {"CONFLICTING", "NEEDS_REVIEW"} for c in CLAIMS),
        "AMBIGUITIES": sum(item["type"] in {"SOURCE_UNCERTAIN", "TRANSCRIPT_CONFLICT", "SEMANTIC_ANOMALY", "INCOMPLETE_STATEMENT"} for item in REVIEW_ITEMS),
        "OPEN_QUESTIONS": sum(len(v) for v in OPEN_QUESTIONS.values()),
        "PROCEDURES": 0,
        "APPLICATIONS_IDENTIFIED": len(APP_SECTIONS),
        "EXTERNAL_VERIFIED_FACTS": 0,
        "MINERU_INTEGRATION": "EVALUATED_NOT_CONNECTED_OR_INSTALLED",
        "SESSION_41_QUALITY_GATE": "FAIL - SOURCE_INCOMPLETE; not FULLY_GROUNDED",
        "quality_gate": gates,
        "source_coverage": coverage,
        "claim_state_counts": {state: sum(c["verification_state"] == state for c in CLAIMS) for state in sorted({c["verification_state"] for c in CLAIMS})},
    }
    (OUT / "quality-report.json").write_text(json.dumps(quality_report, indent=2, ensure_ascii=False), encoding="utf-8")
    session_markdown = markdown_for_session(source, gates, app_markdown, source_map, assets)
    (OUT / "SESSION_MANUAL.md").write_text(session_markdown, encoding="utf-8")
    pdf_sections: list[tuple[str, list[str]]] = [
        ("Source Coverage", [f"Video {coverage['duration_formatted']}; transcript ends {coverage['transcript_last_timestamp_formatted']}; end-time coverage {coverage['transcript_last_timestamp_coverage_percent']:.2f}%; unexplained final gap {coverage['trailing_gap_formatted']}. Visual evidence is sparse sampled imagery, not continuous coverage."]),
        ("Quality Gate Matrix", [f"{name}: {result['status']} - {result['evidence']}" for name, result in gates["gates"].items()]),
    ]
    for app_id, content in APP_SECTIONS.items():
        pdf_sections.append((f"Application: {app_id}", ["Independent mission pack. See its versioned APP_MISSION_PACK artifact for all 18 required operational sections."]))
        pdf_sections.extend(content)
    pdf_sections.extend([
        ("Evidence Timeline", [f"{start}-{end} {app}: {summary} ({', '.join(ids)})" for eid, start, end, app, summary, ids, types in TIMELINE]),
        ("Source Map", [f"{item.get('evidence_id', item.get('source_id'))}: {item.get('path', item.get('source_path'))}; {item.get('source_type')}" for item in source_map]),
        ("Ambiguities and Review", [f"{item['id']} {item['timestamp']}: {item['ambiguity']}" for item in REVIEW_ITEMS]),
    ])
    render_pdf(OUT / "SESSION_MANUAL.pdf", "Session 41 - AMS / Application Support Mission Pack", "Session evidence manual | version 3 | SOURCE_INCOMPLETE", pdf_sections, image_paths=assets)
    quality_report["SESSION_SECTION_COUNT"] = sum(line.startswith("#") for line in session_markdown.splitlines())
    quality_report["NEW_SECTION_COUNT"] = quality_report["SESSION_SECTION_COUNT"] + 2 * 21
    (OUT / "quality-report.json").write_text(json.dumps(quality_report, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "artifact_version": VERSION,
        "session_id": SESSION_ID,
        "previous_version": "000002",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_video_sha256": coverage["video_sha256"],
        "source_coverage_status": coverage["status"],
        "quality_status": gates["status"],
        "fully_grounded": gates["fully_grounded"],
        "outputs": ["SESSION_MANUAL.md", "SESSION_MANUAL.pdf", "knowledge-document.json", "evidence-timeline.json", "review-queue.json", "quality-report.json"],
        "application_packs": {app: {"version": 1, "path": f"apps/{APP_IDS[app]}/v000001"} for app in APP_SECTIONS},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    runtime_version = RUNTIME_ROOT / "documentation_versions" / VERSION
    for subdir in ("manual", "evidence", "applications"):
        (runtime_version / subdir).mkdir(parents=True, exist_ok=True)
    for name in ("SESSION_MANUAL.md", "SESSION_MANUAL.pdf", "knowledge-document.json"):
        shutil.copy2(OUT / name, runtime_version / "manual" / name)
    shutil.copy2(OUT / "SESSION_MANUAL.md", RUNTIME_ROOT / "manual" / "MANUAL.md")
    shutil.copy2(OUT / "SESSION_MANUAL.pdf", RUNTIME_ROOT / "manual" / "MANUAL.pdf")
    shutil.copy2(OUT / "knowledge-document.json", RUNTIME_ROOT / "manual" / "knowledge-document.json")
    for name in ("evidence-timeline.json", "review-queue.json"):
        shutil.copy2(OUT / name, runtime_version / "evidence" / name)
        shutil.copy2(OUT / name, RUNTIME_ROOT / "evidence" / name)
    shutil.copy2(OUT / "SESSION_MANUAL.pdf", runtime_version / "manual" / "MANUAL.pdf")
    (runtime_version / "version.json").write_text(json.dumps({
        "documentation_version": 3,
        "pipeline_version": "documentation-v2-mission-pack-v1",
        "generated_at": manifest["generated_at"],
        "source_video_id": SESSION_ID,
        "source_video_sha256": coverage["video_sha256"],
        "status": "COMPLETED",
        "generation_status": "SOURCE_INCOMPLETE",
        "quality_status": "FAIL",
        "fully_grounded": False,
        "previous_version": 2,
    }, indent=2), encoding="utf-8")
    metadata = {"schema_version": 3, "video_name": SESSION_ID + ".mp4", "duration": coverage["video_duration_seconds"],
                "generated_at": manifest["generated_at"], "documentation_mode": "AMS_SUPPORT_MISSION_PACK",
                "synthesis_status": "SOURCE_INCOMPLETE", "review_required_count": len(REVIEW_ITEMS),
                "quality_gate": "FAIL", "semantic_section_count": quality_report["NEW_SECTION_COUNT"],
                "grounded_claim_count": quality_report["GROUNDED_CLAIMS"], "uncertain_claim_count": quality_report["UNCERTAIN_CLAIMS"]}
    (RUNTIME_ROOT / "manual" / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for app_id in APP_SECTIONS:
        runtime_app = RUNTIME_ROOT / "applications" / APP_IDS[app_id] / "v000001"
        runtime_app.mkdir(parents=True, exist_ok=True)
        (runtime_version / "applications" / APP_IDS[app_id]).mkdir(parents=True, exist_ok=True)
        tracked_app = OUT / "apps" / APP_IDS[app_id] / "v000001"
        for filename in ("APP_MISSION_PACK.md", "APP_MISSION_PACK.pdf", "app-knowledge.json"):
            shutil.copy2(tracked_app / filename, runtime_app / filename)
        for filename in ("APP_MISSION_PACK.md", "APP_MISSION_PACK.pdf", "app-knowledge.json"):
            shutil.copy2(tracked_app / filename, runtime_version / "applications" / APP_IDS[app_id] / filename)
    print(json.dumps(quality_report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    prepare_assets_cache: dict[str, Path] = {}
    main()
