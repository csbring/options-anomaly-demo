# Release validation

Validated locally on 2026-11-17 with Python 3.12.13. CI runs the offline suite on Python 3.11, 3.12 and 3.13.

## Synology release

Public demo: https://cbring.synology.me/options-anomaly/

- **31 tests passed**, including persistent last-run storage across service restarts, TWS-offline fallback, preserving original timestamps, missing-ticker errors, refusing synthetic cache writes, gateway authentication, body limits and request limits.
- The hosted service uses real quote snapshots. TWS was closed during deployment; the initial cache imports the original collector's October 23, 2026 SPY, NVDA and HIMS quote snapshots. Those reports were rescored and labeled as saved historical data. No quote rows, plots of real data, private configuration or source database were committed to GitHub.
- Browser checks cover loading the saved report on arrival/reload, the exact connectivity warning, original collection date, ticker-specific fallback, preserving the visible report when the requested ticker has no cache, follow-up interpretation, chart download and mobile overflow.
- Public request checks confirm unknown routes return 404, cross-origin writes return 403, non-JSON writes return 415 and direct unauthenticated backend requests return 401. Private gateway configuration is not publicly served.
- The original synthetic-mode screenshot and checks below remain applicable to the local default mode. Fresh TWS collection remains unverified until TWS is reopened.

## Initial local demo

- **26 tests passed:** ticker parsing, deterministic fixtures, separate baseline, invalid/crossed quote rejection, missing OI, scenario differences, image/JSON output, report follow-ups, request origin/host/content-type boundaries, sanitized broker errors, optional-model behavior, and mocked TWS collection/cleanup.
- **Real browser checks passed:** desktop 1512px, mobile 390px, bare `AAPL` command, 120 scored quotes, 12 ranked rows, follow-up explanation, wide-spread scenario, rejected invalid input, PNG/CSV downloads, no horizontal page overflow, no JavaScript exceptions.
- **CLI verified:** one machine-readable JSON object plus readable PNG and CSV artifacts.
- **Packaging verified:** wheel build and inclusion of browser assets.
- **Real local Ollama call verified:** `qwen3.5:27b` returned an interpretation of the generated AAPL report and explicitly identified the synthetic data. No market/account data was sent.
- **Public-source secret scan:** Gitleaks found no secrets in the selected public files. Only source, tests, documentation and a screenshot of generated data are included.

Example generated AAPL results with the validation environment:

| Scenario | Quotes | Flagged calls | Flagged puts | Pass quality checks |
| --- | ---: | ---: | ---: | ---: |
| Unusual calls | 120 | 11 | 3 | 11 of 14 |
| Unusual puts | 120 | 6 | 7 | 10 of 13 |
| Activity with poor spreads | 120 | 11 | 3 | 5 of 14 |

These are synthetic demonstrations, not measured market performance. Different supported dependency versions may produce slightly different scores or flags.

Live TWS behavior was not exercised against a brokerage session for this release. Broker tests use a fake IB client and confirm a maximum of 48 contracts, `readonly=True`, disabled startup fetches, underlying contract-ID usage, actual delayed-data labeling, and subscription cleanup after errors. WhatsApp authentication and message delivery are not included or verified.

An initial local Python 3.12.3 runtime stalled in the dependency stack's file-response tests. Validation passed with the current 3.12.13 patch release. Use an up-to-date Python patch release. Current dependencies also emit non-failing deprecation warnings for Starlette's HTTPX test adapter and pandas/NumPy date arithmetic in mocked tests.
