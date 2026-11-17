import asyncio
from collections import OrderedDict
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

STATIC = Path(__file__).parent / "static"
HELP = "Type AAPL, $NVDA or flow SPY to create a report. Then ask why, calls, puts, quality or model. Enable Ollama locally for free-form questions about your report."
FOLLOWUPS = {"why", "explain", "why flagged", "why flagged these", "why these", "calls", "puts", "quality", "spreads", "risk", "model", "method", "how", "summary", "summarize"}


class LocalBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin != str(request.base_url).rstrip("/"):
            return await JSONResponse({"detail": "Use the local demo page."}, status_code=403)(scope, receive, send)
        if request.method == "POST" and not request.headers.get("content-type", "").startswith("application/json"):
            return await JSONResponse({"detail": "JSON required."}, status_code=415)(scope, receive, send)

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
    app.add_middleware(LocalBoundary)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
    reports = OrderedDict()
    lock = asyncio.Lock()
    app.state.reports = reports

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    async def status():
        return {"source": os.getenv("OPTIONS_SOURCE", "synthetic"), "local_model": bool(os.getenv("OLLAMA_MODEL"))}

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
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
                    return {"text": answer, "report_id": body.report_id, "narrator": narrator}
                symbol = parse_symbol(message)
                report = await asyncio.to_thread(analyze, symbol, body.scenario, os.getenv("OPTIONS_SOURCE", "synthetic"))
                generated, narrator = await asyncio.to_thread(narrate, report, "Summarize the key findings and limitations.")
                report_id = secrets.token_urlsafe(24)
                reports[report_id] = (time.monotonic(), report)
                while len(reports) > 16:
                    reports.popitem(last=False)
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
