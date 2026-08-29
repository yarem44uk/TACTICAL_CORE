"""WO-037-05 — Operator-layer authentication / access control.

Minimal, offline-compatible bearer-token auth gate for the operator HTTP
surface (ADR-011 §15). Stdlib only (``secrets.compare_digest``). Operator-local:
this module never imports or depends on the durable core, never writes state,
and never touches the authoritative repositories.

Security model (WO-037-05):
  * credential = ``OPERATOR_TOKEN`` environment variable on the operator process;
  * token comparison = constant-time ``secrets.compare_digest``;
  * gate ENABLED only when a token is configured;
  * gate DISABLED (local dev / tests) when no token is configured;
  * missing/invalid credential -> 401 (never echoes or logs the token);
  * no durable auth state, no second store, no external identity provider.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_ENV = "OPERATOR_TOKEN"


class OperatorAuthError(Exception):
    """Raised when a request does not present a valid operator credential.

    Carries a fixed, non-secret ``detail`` string that is safe to return to a
    client (never a credential, stack trace, or internal detail).
    """

    def __init__(self, detail: str = "authentication required") -> None:
        super().__init__(detail)
        self.detail = detail


def resolve_operator_token() -> Optional[str]:
    """Read the operator credential from the environment (never logs it).

    Returns ``None`` when the variable is unset or empty, meaning the auth
    gate is disabled (local dev / tests).
    """
    token = os.environ.get(TOKEN_ENV, "")
    return token if token else None


def is_auth_gate_enabled(token: Optional[str]) -> bool:
    """A gate is enabled exactly when a non-empty token is configured."""
    return bool(token)


def _extract_bearer(authorization_header: Optional[str]) -> Optional[str]:
    """Return the bearer token from an Authorization header, or None.

    Accepts only the standard ``Authorization: Bearer <token>`` form. Any other
    scheme or malformed form yields ``None`` (treated as missing credential).
    """
    if not authorization_header:
        return None
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


class OperatorAuthGate:
    """Stateless bearer-token gate for the operator HTTP surface.

    The credential is held only in memory for this process instance. The gate
    never writes, never creates state, and never touches the durable
    repositories. When disabled (no token configured) it permits all requests,
    preserving existing local dev / test behavior.
    """

    def __init__(self, token: Optional[str]) -> None:
        self._token = token
        self._enabled = is_auth_gate_enabled(token)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def require(self, authorization_header: Optional[str]) -> None:
        """Validate an Authorization header; raise OperatorAuthError on failure.

        Uses constant-time comparison. Never echoes the presented token and
        never logs it; only logs that a request was rejected.
        """
        if not self._enabled:
            # Gate disabled (no token configured): allow all (dev/test).
            return
        presented = _extract_bearer(authorization_header)
        if presented is None:
            logger.info("operator auth rejected: missing bearer token")
            raise OperatorAuthError("authentication required")
        expected = self._token
        assert expected is not None  # require() only enforces when enabled
        if not secrets.compare_digest(presented, expected):
            logger.warning("operator auth rejected: invalid bearer token")
            raise OperatorAuthError("authentication failed")
        # Success — nothing secret is logged.


def build_operator_auth_gate() -> OperatorAuthGate:
    """Build the gate from the process environment (used by the entrypoint)."""
    return OperatorAuthGate(token=resolve_operator_token())


# -- ASGI middleware ----------------------------------------------------------

from starlette.responses import JSONResponse  # noqa: E402
from starlette.types import ASGIApp, Message, Receive, Scope, Send  # noqa: E402

# Security hardening headers added to every operator HTTP response (WO-037-05).
# These do not touch Cache-Control / X-Accel-Buffering / Connection, so the SSE
# ``text/event-stream`` semantics remain valid.
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'self'; frame-ancestors 'self'",
}


class OperatorAuthMiddleware:
    """Pure-ASGI auth gate wrapping the entire operator application.

    Wrapping at the raw ASGI level (not ``BaseHTTPMiddleware``) guarantees that
    SSE streaming is never buffered: on success the ``receive``/``send``
    callables are passed straight through to the downstream app. On failure a
    401 JSON response is emitted before the route runs, so no stream byte and
    no operator data is produced for an unauthenticated request.

    Because it wraps the whole app, it covers every operator HTTP surface:
    REST, SSE, the offline UI index, and static assets.
    """

    def __init__(self, app: ASGIApp, gate: OperatorAuthGate) -> None:
        self.app = app
        self.gate = gate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        raw = headers.get(b"authorization")
        auth_header = raw.decode("latin-1") if raw is not None else None
        try:
            self.gate.require(auth_header)
        except OperatorAuthError as exc:
            response = JSONResponse(
                status_code=401,
                content={
                    "detail": exc.detail,
                    "error_type": "AuthenticationRequired",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware adding security hardening headers.

    Only modifies the ``http.response.start`` message, so headers are attached
    to the initial HTTP response (including the SSE ``200`` start) without
    touching subsequent ``http.response.body`` frames — SSE framing is safe.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                for name, value in SECURITY_HEADERS.items():
                    headers[name.encode("latin-1")] = value.encode("latin-1")
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)

