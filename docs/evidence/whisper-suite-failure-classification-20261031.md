# Whisper full-suite non-passing classification ? 2026-10-31

Baseline: 1,430 passed, 8 skipped, 5 failed, 6 errors. Only focused validations were rerun; the full suite was not repeated.

| Case | Classification | Evidence / disposition |
|---|---|---|
| `tests/integration/test_dashboard_process_restart.py::test_dashboard_real_process_restart_has_fresh_run_state` | ENVIRONMENTAL | Child inherited host `.env` LAN TLS settings. Test now supplies isolated temporary data root, disables LAN/container TLS, and empties cert/key values. Focused rerun passed. |
| `tests/integration/test_live_capture_pipeline.py::test_finalized_chunk_with_audio_flows_to_docs` | STALE_TEST | Six-second fixture fails required transcript/visual gates and must remain diagnostic-only. Expectation updated; focused rerun passed. |
| `tests/test_documentation_v2_knowledge_bridge.py::test_package_artifact...` | REGRESSION_FROM_CURRENT_CHANGE | Disabling the legacy publisher also removed local candidate package output. Restored local package generation without publishing/indexing. Focused documentation bridge file: 5 passed. |
| `tests/test_documentation_v2_knowledge_bridge.py::test_procedure_artifact...` | REGRESSION_FROM_CURRENT_CHANGE | Same regression and fix as above; local artifact generation stays available, publisher/indexer remain disabled. Focused documentation bridge file: 5 passed. |
| `tests/test_restart_recovery.py::test_run_state_resets_on_restart` | ENVIRONMENTAL | Test shared the live ProcessingWorker store; isolated the worker state in the test. Focused rerun passed. |
| `tests/integration/test_lan_https_server.py::test_server_binds...` | ENVIRONMENTAL | Python 3.14 pip vendored truststore calls `sslobj.get_unverified_chain()` on a `None` SSL object; setup error occurs before product assertion. |
| `tests/integration/test_lan_https_server.py::test_served_chain...` | ENVIRONMENTAL | Same Python 3.14 truststore setup failure. |
| `tests/integration/test_lan_https_server.py::test_health_and_files...` | ENVIRONMENTAL | Same Python 3.14 truststore setup failure. |
| `tests/integration/test_lan_https_server.py::test_lan_interface...` | ENVIRONMENTAL | Same Python 3.14 truststore setup failure. |
| `tests/integration/test_lan_https_server.py::test_synthetic_upload...` | ENVIRONMENTAL | Same Python 3.14 truststore setup failure. |
| `tests/integration/test_lan_https_server.py::test_separate_process_health...` | ENVIRONMENTAL | Same Python 3.14 truststore setup failure. |

## Counts

- `REGRESSION_FROM_CURRENT_CHANGE=2` (fixed; focused tests pass)
- `PREEXISTING=0` (no case evidenced as an unrelated pre-existing product defect)
- `ENVIRONMENTAL=8` (two restart isolation issues fixed; six TLS setup errors remain environmental)
- `STALE_TEST=1` (expectation corrected; focused test passes)
- `RESOURCE=0`, `REAL_PRODUCT_DEFECT=0`

The six LAN HTTPS errors remain bounded to Python 3.14 truststore setup. Do not treat them as a product pass; rerun those tests under the supported Python 3.12 runtime when available. No full-suite rerun was performed.
