#!/usr/bin/env python3
"""Provision the dashboard HTTPS certificate/key for mobile/LAN access (W25).

Thin wrapper around `transcript_pipeline.lan_access.main` so the certificate
can be generated without installing the console entry points:

    python scripts/setup_lan_certificate.py --host whisper.local

The certificate is written to the gitignored `<DATA_ROOT>/lan-access/`
directory by default. The private key is never printed. See
`docs/ops/MOBILE_LAN_ACCESS.md` for phone trust installation steps.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from transcript_pipeline.lan_access import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
