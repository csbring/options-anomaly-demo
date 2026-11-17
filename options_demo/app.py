import asyncio
from collections import OrderedDict
import hmac
import os
from pathlib import Path
import secrets
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .analysis import analyze, explain, parse_symbol
from .narration import narrate
from .store import ReportStore
from .tws import TWSUnavailable, reachable

STATIC = Path(__file__).parent / "static"
HELP = "Type AAPL, $NVDA or flow SPY to create a report. Then ask why, calls, puts, quality or model. Enable Ollama locally for free-form questions about your report."
FOLLOWUPS = {"why", "explain", "why flagged", "why flagged these", "why these", "calls", "puts", "quality", "spreads", "risk", "model", "method", "how", "summary", "summarize"}


class LocalBoundary:
    def __init__(self, app, gateway_key=""):
        self.app = app
        self.gateway_key = gateway_key

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        if self.gateway_key and not hmac.compare_digest(request.headers.get("x-demo-gateway", ""), self.gateway_key):
            return await JSONResponse({"detail": "Gateway authentication required."}, status_code=401)(scope, receive, send)
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin != str(request.base_url).rstrip("/"):
            return await JSONResponse({"detail": "Use the local demo page."}, status_code=403)(scope, receive, send)
        if request.method == "POST" and not request.headers.get("content-type", "").startswith("application/json"):
            return await JSONResponse({"detail": "JSON required."}, status_code=415)(scope, receive, send)
        if request.method == "POST":
            body = b""
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                body += chunk.get("body", b"")
                if len(body) > 4096:
                    return await JSONResponse({"detail": "Request too large."}, status_code=413)(scope, receive, send)
                if not chunk.get("more_body", False):
                    break
            original_receive = receive
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()
            receive = bounded_receive

        async def with_headers(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"content-security-policy", b"default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"),
                ]
            await send(message)
        await self.app(scope, receive, with_headers)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=240)
    report_id: str | None = Field(default=None, max_length=100)
    scenario: Literal["call_activity", "put_activity", "wide_spreads"] = "call_activity"


def create_app():
    app = FastAPI(title="Options Anomaly Lab", docs_url=None, redoc_url=None)
    public = os.getenv("OPTIONS_PUBLIC", "0") == "1"
    gateway_key = os.getenv("OPTIONS_GATEWAY_KEY", "")
    if public and len(gateway_key) < 32:
        raise RuntimeError("Public mode requires a private gateway key.")
    app.add_middleware(LocalBoundary, gateway_key=gateway_key)
    hosts = ["127.0.0.1", "localhost", "[::1]", "testserver"] + os.getenv("OPTIONS_ALLOWED_HOSTS", "").split(",")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h for h in hosts if h])
    reports = OrderedDict()
    admissions = OrderedDict()
    lock = asyncio.Lock()
    source = os.getenv("OPTIONS_SOURCE", "synthetic")
    default_dir = str(Path.home() / ".local/share/options-anomaly-demo/reports") if source == "tws" else None
    store = ReportStore(os.getenv("OPTIONS_REPORT_DIR", default_dir))
    app.state.reports = reports
    app.state.store = store

    def remember(report):
        for key in list(reports):
            if time.monotonic()-reports[key][0] > 1800:
                reports.pop(key)
        report_id = secrets.token_urlsafe(24)
        reports[report_id] = (time.monotonic(), report)
        while len(reports) > 16:
            reports.popitem(last=False)
        return report_id

    def saved_response(report, warning):
        report = dict(report, availability={"cached": True, "message": warning})
        return {"text": warning + " " + report["summary"], "narrator": "Last saved run", "report_id": remember(report), "report": report}

    def rate_limit(request):
        if not public:
            return
        now = time.monotonic()
        for key in list(admissions):
            if now - admissions[key][0] > 3600:
                admissions.pop(key)
        client = request.headers.get("x-demo-client", "unknown")[:100]
        for key, window, limit in (("global", 3600, 120), ("client:"+client, 300, 12)):
            started, count = admissions.get(key, (now, 0))
            if now-started >= window:
                started, count = now, 0
            if count >= limit:
                raise HTTPException(429, "Demo request limit reached. Please try again later.")
            admissions[key] = (started, count+1)
        while len(admissions) > 1024:
            key = next(k for k in admissions if k != "global")
            admissions.pop(key)

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    async def status():
        return {"source": source, "local_model": bool(os.getenv("OLLAMA_MODEL")), "public": public, "tws_reachable": await asyncio.to_thread(reachable) if source == "tws" else None}

    @app.get("/api/last")
    async def last():
        report = store.load()
        connected = await asyncio.to_thread(reachable) if source == "tws" else False
        prefix = "TWS connectivity is not available. " if not connected else ""
        if report is None:
            return {"report": None, "text": prefix + "No successful run has been saved yet."}
        return saved_response(report, prefix + f"Displaying last run for {report['symbol']} — data collected {report['metadata']['quote_time']}. Enter a ticker to request a fresh scan.")

    @app.post("/api/chat")
    async def chat(body: ChatRequest, request: Request):
        rate_limit(request)
        message = body.message.strip()
        lower = message.lower().rstrip("?")
        if lower in ("help", "hello", "hi"):
            return {"text": HELP, "report_id": body.report_id, "narrator": "Guide"}
        if not message:
            raise HTTPException(400, "Enter a ticker or question.")
        if lock.locked():
            raise HTTPException(429, "An analysis is already running. Try again shortly.")
        async with lock:
            for key in list(reports):
                if time.monotonic()-reports[key][0] > 1800:
                    reports.pop(key)
            try:
                if lower in FOLLOWUPS or (body.report_id and len(message.split()) > 1 and not lower.startswith(("flow ", "!flow ", "/flow ", "analyze ", "scan "))):
                    if body.report_id not in reports:
                        raise HTTPException(400, "Enter a ticker first; this report may have expired.")
                    report = reports[body.report_id][1]
                    generated, narrator = await asyncio.to_thread(narrate, report, message)
                    answer = generated or explain(report, message)
                    if report.get("availability", {}).get("cached"):
                        answer = f"Based on the saved run collected {report['metadata']['quote_time']}. " + answer
                    return {"text": answer, "report_id": body.report_id, "narrator": narrator}
                symbol = parse_symbol(message)
                try:
                    report = await asyncio.to_thread(analyze, symbol, body.scenario, source)
                except Exception as exc:
                    if source != "tws":
                        raise
                    warning = "TWS connectivity is not available." if isinstance(exc, TWSUnavailable) else "TWS could not complete a usable quote snapshot."
                    saved = store.load(symbol)
                    if saved:
                        return saved_response(saved, warning + f" Displaying last run for {symbol} — data collected {saved['metadata']['quote_time']}.")
                    raise HTTPException(503, warning + f" No saved run for {symbol}. Any previous report remains displayed.") from None
                report["availability"] = {"cached": False, "message": ""}
                store.save(report)
                generated, narrator = (None, "Structured explanation") if source == "tws" else await asyncio.to_thread(narrate, report, "Summarize the key findings and limitations.")
                report_id = remember(report)
                return {"text": generated or report["summary"], "narrator": narrator, "report_id": report_id, "report": report}
            except HTTPException:
                raise
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None
            except Exception:
                # Raw broker errors can include private runtime details.
                raise HTTPException(503, "Analysis unavailable. Check local TWS settings or restart in synthetic mode.") from None

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
