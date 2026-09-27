# Community Launch Checklist — Zo Media Intelligence

This checklist is executed only after `US-ZMI-001` is `READY_FOR_HUMAN_ACCEPTANCE` and the owner passes the final local product check.

## Code/repository gates

- [ ] PR #24 (or its successor clean integration PR) audited.
- [ ] quality/security/unit/smoke/E2E/fresh-install checks green.
- [ ] local private identifier tree scan = 0.
- [ ] local private identifier full-history scan = 0.
- [ ] no unresolved P0/P1 finding.
- [ ] final owner dashboard flow passes on real local machine.

## Repository metadata

- [ ] Rename repository `zo_whisper2` -> `zo-media-intelligence`.
- [ ] Description:
  `Local-first multimodal media intelligence that turns screen recordings into evidence-grounded documentation and AI-ready knowledge.`
- [ ] Topics:
  `ai`, `python`, `whisper`, `faster-whisper`, `ffmpeg`, `ocr`, `rag`, `multimodal-ai`, `local-first`, `playwright`, `llm`, `knowledge-management`.
- [ ] Enable Discussions for community Q&A/ideas.
- [ ] Verify README badges/links after rename.

## Release

- [ ] Tag `v1.1.0` exactly on the audited/accepted main SHA.
- [ ] Publish GitHub Release from `CHANGELOG.md` highlights.
- [ ] Attach/link synthetic demo assets only.
- [ ] Confirm no real recordings/transcripts/private paths in release assets.

## Community bootstrap

- [ ] Open a small set of real `good first issue` / `help wanted` tasks from P2/P3 backlog.
- [ ] Confirm bug/feature templates and PR template render correctly.
- [ ] Confirm security reporting instructions are visible.
- [ ] Publish LinkedIn launch using **Zo Media Intelligence** branding.

Do not claim SOC 2 compliance. Enterprise trust/compliance readiness is a future feature until an independent audit/attestation exists.
