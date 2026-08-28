"""WO-037-02 — Operator FastAPI application factory.

Constructs the separate read-only operator FastAPI application (ADR-011).

Architecture:
  * the operator process is a CONSUMER of the authoritative durable engine;
  * it exposes only the GET-only operator API under ``/api/v1/operator``;
  * it is independent from ``backend/main.py`` — it never starts the durable
    engine, never creates a second database or event store;
  * dependency injection is plain constructor wiring: the factory accepts
    optional authoritative repositories (defaulting to those bound to the
    global ``DatabaseSessionManager``), so tests can inject isolated
    repositories / test doubles without touching the durable engine.

The factory does NOT launch uvicorn. The separate ``entrypoint`` does that.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database.session import get_session_manager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.operator.router import router
from app.operator.service import (
    InvalidRequestError,
    NotFoundError,
    OperatorError,
    OperatorService,
    ReadDependencyUnavailableError,
)

API_PREFIX = "/api/v1/operator"

# Directory containing the offline operator UI static assets (WO-037-03).
STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = logging.getLogger(__name__)


def _default_event_repository() -> SQLAlchemyEventRepository:
    return SQLAlchemyEventRepository(session_manager=get_session_manager())


def _default_entity_repository() -> SQLAlchemyEntityRepository:
    return SQLAlchemyEntityRepository(session_manager=get_session_manager())


def _default_relation_repository() -> SQLAlchemyRelationRepository:
    return SQLAlchemyRelationRepository(session_manager=get_session_manager())


def create_operator_app(
    *,
    event_repository: Optional[SQLAlchemyEventRepository] = None,
    entity_repository: Optional[SQLAlchemyEntityRepository] = None,
    relation_repository: Optional[SQLAlchemyRelationRepository] = None,
    title: str = "Tactical Core Operator API",
    version: str = "1.0.0",
) -> FastAPI:
    """Construct the read-only operator FastAPI application.

    Args:
        event_repository: optional injected authoritative event repository.
        entity_repository: optional injected authoritative entity repository.
        relation_repository: optional injected authoritative relation repository.
        title: application title (OpenAPI).
        version: application version (OpenAPI).

    Returns:
        A configured FastAPI application exposing the GET-only operator API.

    Raises:
        RuntimeError: if no repositories are injected AND the global session
            manager is not configured (operator cannot reach the authoritative
            database at construction time).
    """
    if event_repository is None:
        event_repository = _default_event_repository()
    if entity_repository is None:
        entity_repository = _default_entity_repository()
    if relation_repository is None:
        relation_repository = _default_relation_repository()

    service = OperatorService(
        event_repository=event_repository,
        entity_repository=entity_repository,
        relation_repository=relation_repository,
    )

    app = FastAPI(title=title, version=version)
    app.state.operator_service = service
    app.include_router(router)

    # -- offline operator UI (WO-037-03) ------------------------------------
    # Served ONLY by this operator process (ADR-011 §13). Self-contained
    # local HTML/CSS/JS with zero external/CDN dependencies. Mounted read-only
    # static assets plus an explicit index route. This never touches the
    # durable engine and is independent of backend/main.py.
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def _operator_index() -> HTMLResponse:
            index_file = STATIC_DIR / "index.html"
            if not index_file.is_file():
                return HTMLResponse(
                    content="<h1>Tactical Core Operator UI</h1><p>index.html not found</p>",
                    status_code=503,
                )
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    # -- structured error contract (400 / 404 / 503 / 500) --------------------
    # Registered on the app instance (APIRouter has no exception_handler).

    @app.exception_handler(InvalidRequestError)
    async def _invalid_request(
        request: Request, exc: InvalidRequestError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_type": type(exc).__name__},
        )

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_type": type(exc).__name__},
        )

    @app.exception_handler(ReadDependencyUnavailableError)
    async def _read_unavailable(
        request: Request, exc: ReadDependencyUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_type": type(exc).__name__},
        )

    @app.exception_handler(OperatorError)
    async def _operator_error(
        request: Request, exc: OperatorError
    ) -> JSONResponse:
        # Unexpected operator-layer error -> 500 (no internals exposed).
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_type": type(exc).__name__},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's built-in parameter validation defaults to 422; the operator
        # error contract requires 400 for invalid request/parameter.
        return JSONResponse(
            status_code=400,
            content={
                "detail": "invalid request parameter",
                "error_type": "InvalidRequestError",
            },
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Any other unexpected operator-layer error -> generic 500. Log the real
        # exception server-side for diagnostics, but never expose credentials,
        # SQL internals, stack traces or secrets to API clients.
        logger.exception(
            "unhandled operator error on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "internal operator error",
                "error_type": "InternalServerError",
            },
        )

    return app
