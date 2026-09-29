"""The Atlas API.

    uvicorn atlas.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import db
from ..config import get_settings
from ..errors import MESSAGES, AtlasError, new_reference
from ..logs import setup_logging
from .analysis import router as analysis_router
from .datasets import router as datasets_router

log = logging.getLogger("atlas.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    db.pool()
    yield
    db.close_pool()


def _internal_error(request: Request) -> JSONResponse:
    reference = new_reference()
    log.exception("unhandled error", extra={"reference": reference, "route": request.url.path})
    return JSONResponse(
        {"error": {"code": "internal_error", "message": MESSAGES["internal_error"].format(reference=reference), "reference": reference}},
        status_code=500,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.environment != "production"
    app = FastAPI(
        title="Atlas API",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    @app.middleware("http")
    async def guard_and_log(request: Request, call_next):
        started = time.monotonic()
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_upload_bytes + 1024 * 1024:
            error = AtlasError("file_too_large", status_code=413, limit_mb=settings.max_upload_mb)
            return JSONResponse({"error": error.to_dict()}, status_code=413)
        try:
            response = await call_next(request)
        except Exception:
            # Handled here rather than by the Exception handler below:
            # Starlette runs that handler outside every middleware, so its
            # 500 would carry no CORS headers and the browser would report
            # "couldn't reach Atlas" instead of the real message.
            response = _internal_error(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        route = request.scope.get("route")
        log.info(
            "request",
            extra={
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status": response.status_code,
                "ms": int((time.monotonic() - started) * 1000),
                "org_id": getattr(request.state, "org_id", None),
            },
        )
        return response

    @app.exception_handler(AtlasError)
    async def atlas_error(_: Request, error: AtlasError):
        return JSONResponse({"error": error.to_dict()}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError):
        return JSONResponse({"error": {"code": "bad_request", "message": "The request wasn't valid."}}, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, error: StarletteHTTPException):
        code = "not_found" if error.status_code == 404 else "bad_request"
        message = MESSAGES["not_found"] if error.status_code == 404 else "The request wasn't valid."
        return JSONResponse({"error": {"code": code, "message": message}}, status_code=error.status_code)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, _: Exception):
        return _internal_error(request)

    # Added last so it wraps everything above: every response, including the
    # 413 from guard_and_log and unexpected 500s, gets CORS headers, so the
    # web app can show the real error instead of a network failure.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        # The web app reads the download's file name from this header.
        expose_headers=["Content-Disposition"],
        max_age=600,
    )

    @app.get("/healthz", include_in_schema=False)
    def health() -> dict:
        return {"ok": True}

    app.include_router(datasets_router)
    app.include_router(analysis_router)
    return app


app = create_app()
