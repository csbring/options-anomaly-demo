# Synology deployment

Public demo: https://cbring.synology.me/options-anomaly/

The NAS serves `index.php`, `api.php` and the three static files. A separate user service runs the Python backend on the owner's machine. `api.php` forwards only `GET /api/status`, `GET /api/last` and `POST /api/chat`. It authenticates to the backend using a randomly generated gateway key stored outside the web root. The browser never receives that key.

`options-anomaly-demo.service` loads its private environment from `~/.config/options-anomaly-demo/runtime.env`. Required deployment variables:

- `OPTIONS_PUBLIC=1`
- `OPTIONS_SOURCE=tws`
- `OPTIONS_BIND_HOST` and `OPTIONS_ALLOWED_HOSTS`: the backend's LAN address
- `OPTIONS_GATEWAY_KEY`: at least 32 characters, generated independently for this deployment
- `OPTIONS_REPORT_DIR`: private persistent report directory outside the repository
- `TWS_HOST`, `TWS_PORT`, `TWS_CLIENT_ID`, `TWS_MARKET_DATA_TYPE`: local broker settings
- Optional `OLLAMA_MODEL`: installed local model for report follow-ups

The private PHP configuration contains `key`, `backend` and `origin`. Replace the `__PRIVATE_CONFIG_PATH__` placeholder in a deployment copy of `api.php`; never commit the private configuration or modified secret material. Only the NAS web worker and owner need read access to that configuration.

The public gateway rejects unknown routes, cross-origin POSTs, non-JSON POSTs and bodies over 4 KiB. Backend public mode requires the gateway key and limits chat requests to 12 per client per five minutes and 120 globally per hour. Only one analysis/model request runs at a time. Public users cannot choose a broker host, port, file path or data source.

DSM replaces HTTP 5xx responses with an HTML error page. The PHP gateway therefore wraps upstream application failures in HTTP 200 JSON with `error: true`, the original numeric `status`, and `detail`. The frontend checks that envelope before updating any report. Gateway access/method/origin denials retain their HTTP error status. Direct backend responses use normal HTTP status codes.

TWS connectivity is checked on page arrival. Last successful quote reports are stored atomically with private file permissions, bounded to 50 symbols, and survive service restarts. Offline responses retain the original collection timestamp and are labeled “last saved run.” If a requested ticker has no saved run, the error says so and the currently displayed report remains visible. Reopening TWS allows the next ticker request to collect a new snapshot.

The deployed starter cache contains only selected quote reports from the original collector, not the collector database, account data or historical chat logs. Runtime reports and secrets are excluded from GitHub. The README screenshot remains synthetic.
