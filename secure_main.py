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
    try:
        await legifrance_connector.ping()
        return JSONResponse(
            {"status": "connected", "oauth": "ok", "api": "ok",
             "environment": legifrance_connector.environment},
            headers={"Cache-Control": "no-store"},
        )
    except LegifranceUnavailable as exc:
        diagnostic_code = _piste_diagnostic_code(exc)
        # Log only a controlled category and exception class: never upstream
        # messages, request URLs, headers, tokens, or credential values.
        _piste_logger.warning(
            "PISTE health check failed: code=%s exception_type=%s",
            diagnostic_code, type(exc).__name__,
        )
        return JSONResponse(
            {"status": "unavailable", "environment": legifrance_connector.environment,
             "diagnostic_code": diagnostic_code,
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
