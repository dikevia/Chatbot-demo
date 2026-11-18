"""Access gate for the public Dikevia demo.

Set DIKEVIA_DEMO_USER and DIKEVIA_DEMO_PASSWORD in the hosting provider's
secret/environment settings. Never put their values in this repository.
The hosting provider must serve the app over HTTPS.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import logging
import os
from pathlib import Path
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send
import httpx


def _required_secret(name: str, minimum: int = 1) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum:
        raise RuntimeError(
            f"{name} must be configured in the hosting environment "
            f"(minimum {minimum} characters). Refusing to start without demo access credentials."
        )
    return value


class BasicAuthGate:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.username = _required_secret("DIKEVIA_DEMO_USER", 3).encode()
        self.password = _required_secret("DIKEVIA_DEMO_PASSWORD", 24).encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Render needs an unauthenticated HTTP 2xx health check. This endpoint
        # reveals no application data and grants no access to chatbot routes.
        if scope.get("path") == "/_render-health" and scope.get("method") == "GET":
            body = b"ok"
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"")
        valid = False
        if authorization.startswith(b"Basic "):
            try:
                decoded = base64.b64decode(authorization[6:], validate=True)
                supplied_user, supplied_password = decoded.split(b":", 1)
                valid = (
                    hmac.compare_digest(supplied_user, self.username)
                    and hmac.compare_digest(supplied_password, self.password)
                )
            except (binascii.Error, ValueError):
                valid = False

        if valid:
            await self.app(scope, receive, send)
            return

        body = b"Authentification requise pour la demonstration Dikevia."
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"www-authenticate", b'Basic realm="Dikevia Demo", charset="UTF-8"'),
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": body})


# Import only after the gate module is loaded; the gate wraps every HTTP route,
# including the home page, the application health endpoint and the chatbot API.
from dev_main import app as chatbot_app  # noqa: E402

# Diagnostic PISTE endpoint: protected by BasicAuthGate like every app route.
# It reveals only whether OAuth + the official Légifrance ping work; never IDs,
# tokens, secrets, response bodies, or upstream exception details.
from fastapi.responses import JSONResponse  # noqa: E402
from app.legifrance import connector as legifrance_connector, LegifranceUnavailable  # noqa: E402


_piste_logger = logging.getLogger("dikevia.piste")

# Observe only PISTE host role, HTTP status and exception class. Never record
# request headers, bodies, URLs, tokens or credential values.
_piste_last_upstream: dict[str, object] = {}
_original_async_client_send = httpx.AsyncClient.send

async def _piste_observed_send(self, request, *args, **kwargs):
    host = request.url.host.lower()
    if host in {"sandbox-oauth.piste.gouv.fr", "oauth.piste.gouv.fr"}:
        stage = "oauth"
    elif host in {"sandbox-api.piste.gouv.fr", "api.piste.gouv.fr"}:
        stage = "legifrance_api"
    else:
        return await _original_async_client_send(self, request, *args, **kwargs)
    _piste_last_upstream.clear()
    _piste_last_upstream.update({
        "stage": stage, "status": None, "error_type": None, "oauth_error": None,
        "method": request.method.upper(),
        "endpoint": (
            request.url.path.rsplit("/", 2)[-2] + "/" + request.url.path.rsplit("/", 2)[-1]
            if request.url.path.endswith("/legiPart") else
            next((name for name in ("ping", "search") if request.url.path.endswith("/" + name)), "other")
        ),
        "content_type": None, "response_json_keys": None, "api_error_code": None,
    })
    try:
        response = await _original_async_client_send(self, request, *args, **kwargs)
    except Exception as exc:
        _piste_last_upstream["error_type"] = type(exc).__name__
        raise
    _piste_last_upstream["status"] = int(response.status_code)
    _piste_last_upstream["content_type"] = response.headers.get("content-type", "")[:80]
    if stage == "legifrance_api" and response.status_code >= 400:
        # Keep only JSON key names and a short machine-readable code. Never
        # retain response messages, payload values, IDs, headers or tokens.
        try:
            payload = response.json()
            if isinstance(payload, dict):
                _piste_last_upstream["response_json_keys"] = sorted(
                    str(key)[:40] for key in payload.keys()
                )[:12]
                import re
                for key in ("code", "errorCode", "error_code", "type", "error"):
                    value = payload.get(key)
                    # Upstream APIs may encode machine error codes as strings
                    # or integers. Accept only bounded scalar codes; never
                    # retain nested objects, free-form messages or details.
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value):
                        _piste_last_upstream["api_error_code"] = value
                        break
                    if type(value) is int and 0 <= value <= 999999:
                        _piste_last_upstream["api_error_code"] = str(value)
                        break
        except Exception:
            pass
    if stage == "oauth" and response.status_code >= 400:
        # Expose only a standard OAuth error code from a strict allowlist.
        # Never expose error_description, response bodies, or credential data.
        try:
            payload = response.json()
            oauth_error = payload.get("error") if isinstance(payload, dict) else None
            if oauth_error in {
                "invalid_request", "invalid_client", "invalid_grant",
                "unauthorized_client", "unsupported_grant_type", "invalid_scope",
                "access_denied", "temporarily_unavailable", "server_error",
            }:
                _piste_last_upstream["oauth_error"] = oauth_error
        except Exception:
            pass
    return response

# The connector uses httpx.AsyncClient; this wrapper does not alter requests.
httpx.AsyncClient.send = _piste_observed_send

def _piste_observed_failure_code() -> str:
    stage = _piste_last_upstream.get("stage")
    status = _piste_last_upstream.get("status")
    error_type = str(_piste_last_upstream.get("error_type") or "").lower()
    if status in (401, 403):
        return "authentication_rejected"
    if status == 404:
        return "endpoint_not_found"
    if isinstance(status, int) and status >= 500:
        return "upstream_server_error"
    if "timeout" in error_type:
        return "network_timeout"
    if any(token in error_type for token in ("connect", "network", "dns", "socket")):
        return "network_connection_error"
    if isinstance(status, int) and status >= 400:
        return "upstream_http_error"
    if stage:
        return "connector_processing_error"
    return "no_upstream_request"


def _piste_diagnostic_code(exc: BaseException) -> str:
    """Return a safe, non-secret category for a failed upstream request."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None) or getattr(current, "status_code", None)
        if status in (401, 403):
            return "authentication_rejected"
        if status == 404:
            return "endpoint_not_found"
        if isinstance(status, int) and status >= 500:
            return "upstream_server_error"
        name = type(current).__name__.lower()
        if "timeout" in name:
            return "network_timeout"
        if any(token in name for token in ("connect", "network", "dns", "socket")):
            return "network_connection_error"
        current = current.__cause__ or current.__context__
    return "connector_error"


async def _dikevia_piste_health():
    if not legifrance_connector.configured:
        return JSONResponse(
            {"status": "not_configured", "environment": legifrance_connector.environment},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    _piste_last_upstream.clear()
    try:
        await legifrance_connector.ping()
        return JSONResponse(
            {"status": "connected", "oauth": "ok", "api": "ok",
             "environment": legifrance_connector.environment},
            headers={"Cache-Control": "no-store"},
        )
    except LegifranceUnavailable as exc:
        diagnostic_code = _piste_diagnostic_code(exc)
        if diagnostic_code == "connector_error":
            diagnostic_code = _piste_observed_failure_code()
        stage = _piste_last_upstream.get("stage")
        status = _piste_last_upstream.get("status")
        upstream_error_type = _piste_last_upstream.get("error_type")
        # Only controlled metadata is logged and returned.
        _piste_logger.warning(
            "PISTE health check failed: code=%s stage=%s method=%s endpoint=%s status=%s api_error_code=%s response_json_keys=%s content_type=%s oauth_error=%s upstream_error_type=%s exception_type=%s",
            diagnostic_code, stage or "unknown", _piste_last_upstream.get("method"),
            _piste_last_upstream.get("endpoint"), status,
            _piste_last_upstream.get("api_error_code"),
            _piste_last_upstream.get("response_json_keys"),
            _piste_last_upstream.get("content_type"),
            _piste_last_upstream.get("oauth_error"), upstream_error_type, type(exc).__name__,
        )
        return JSONResponse(
            {"status": "unavailable", "environment": legifrance_connector.environment,
             "diagnostic_code": diagnostic_code,
             "diagnostic_stage": stage, "upstream_status": status,
             "upstream_method": _piste_last_upstream.get("method"),
             "upstream_endpoint": _piste_last_upstream.get("endpoint"),
             "upstream_content_type": _piste_last_upstream.get("content_type"),
             "upstream_response_json_keys": _piste_last_upstream.get("response_json_keys"),
             "upstream_api_error_code": _piste_last_upstream.get("api_error_code"),
             "upstream_error_type": upstream_error_type,
             "upstream_oauth_error": _piste_last_upstream.get("oauth_error"),
             "message": "Authentification ou point de contrôle Légifrance indisponible."},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )


chatbot_app.add_api_route("/_piste-health", _dikevia_piste_health, methods=["GET"], include_in_schema=False)

# Le kit sert son index.html à la racine, avec app.js/app.css/config.js
# référencés par des chemins relatifs. Le montage initial /static ne les
# rendait pas accessibles et l'interface apparaissait sans style/fonctionnement.
# On retire uniquement la route "/" qui renvoyait le HTML seul, puis on sert
# tout le dossier frontend à la racine. Les routes API et /health restent avant.
chatbot_app.router.routes = [
    route for route in chatbot_app.router.routes
    if getattr(route, "path", None) != "/"
]
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
chatbot_app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

app = BasicAuthGate(chatbot_app)
