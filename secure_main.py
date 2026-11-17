"""Access gate for the public Dikevia demo.

Set DIKEVIA_DEMO_USER and DIKEVIA_DEMO_PASSWORD in the hosting provider's
secret/environment settings. Never put their values in this repository.
The hosting provider must serve the app over HTTPS.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import os
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

app = BasicAuthGate(chatbot_app)
