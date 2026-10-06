# FEATURE-ZMI-DKR-004 — Low-Token Delivery Evidence

## Outcome

The local coding agent writes code and triggers validation, then exits. Deterministic infrastructure produces compact evidence for owner + heavy-model review.

## Agent boundary

The coding agent:
1. reads frozen US + PLAN;
2. implements;
3. runs only cheap targeted checks while coding;
4. commits + pushes;
5. triggers Jenkins;
6. exits.

It must not:
- watch Jenkins;
- repeatedly poll test processes;
- read full logs unless explicitly asked in a later repair iteration;
- autonomously redefine expected behavior;
- enter an unbounded fix loop.

Preferred coding model: the already-paid lightweight GLM coder pool.

## Jenkins matrix

```
targeted
-> pytest unit/integration
-> quality
-> security
-> docker-config/build
-> docker-smoke
-> Playwright behavior
-> E2E
-> SonarQube (when configured)
-> optional soak
-> aggregate
-> archive
-> one email
```

## Result contract

Each gate writes one compact JSON. Raw output remains only as archived logs/traces.

```
artifacts/US-ZMI-DKR-001/<build>/
  SUMMARY.json
  SUMMARY.md
  targeted.json
  pytest.json
  quality.json
  security.json
  docker-build.json
  docker-smoke.json
  playwright.json
  e2e.json
  sonar.json
  logs/
  traces/
```

`SUMMARY.json` contains:
- US id;
- commit SHA;
- Jenkins build;
- overall status;
- started/finished timestamps;
- every gate status/count/duration;
- failed gate names;
- compact failure signatures;
- artifact locations.

## Email

One message at pipeline completion, not one message per gate.

Subject:
`[ZMI][US-ZMI-DKR-001][BUILD #N] PASS|FAIL`

Body:
- commit;
- compact gate table;
- failed test names/signatures only;
- Jenkins/artifact link;
- `REVIEW_REQUIRED`.

Jenkins email is a notification channel; archived artifacts are the source of truth.
