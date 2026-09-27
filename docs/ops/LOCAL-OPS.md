# Local / CI Operations — Zo Media Intelligence

Zo Media Intelligence uses two complementary validation layers:

- **GitHub Actions**: lightweight, public pull-request checks for community contributions.
- **Jenkins**: local/self-hosted, long-running or soak validation where compute duration and local media/tooling make hosted CI a poor fit.

Neither layer replaces the deterministic repository scripts.

## Fast local gates

```bash
python scripts/gate_runner.py targeted tests/test_project_override.py
python scripts/gate_runner.py quality
python scripts/gate_runner.py security
python scripts/gate_runner.py smoke
```

Compact results are written under `artifacts/gates/` and are gitignored.

## Browser E2E

Use synthetic data only:

```bash
python docs/assets/generate_mock_data.py
python -m playwright install chromium
python scripts/gate_runner.py e2e
python docs/assets/cleanup_mock_data.py
```

Zo Media Intelligence is a web application; its UI adapter is Playwright Chromium. Electron is not a dependency of this product.

## Jenkins

`Jenkinsfile` orchestrates:
`targeted -> quality -> security -> Playwright -> SonarQube -> full E2E -> optional soak -> artifacts`.

SonarQube credentials/URL are supplied by the local Jenkins environment. If SonarQube is not configured, Jenkins records `NOT_CONFIGURED`; it never invents a PASS.

## GitHub Actions

`.github/workflows/dashboard-ci.yml` runs the public PR contract:
quality, security, unit tests, smoke, E2E and fresh-install acceptance.

`.github/workflows/secret-scan.yml` runs Gitleaks against full checkout history.

The maintainer-only private identifier denylist is intentionally not committed. Public CI may report that private sub-check as skipped; the independent Gitleaks/pattern/security tests still run publicly, while the maintainer runs the private denylist locally before release.

## Project-lead V4

`opencode.json` denies native `question` and `doom_loop` prompts project-wide so routine implementation cannot interrupt the owner. Legitimate blockers are returned as typed V4 terminal states.

Runtime checkpoints and gate artifacts stay local:
- `.agents/session/`
- `.agents/memory/`
- `artifacts/`
