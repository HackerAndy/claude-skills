"""Starts one trace per HTTP request. Add once in app/main.py:

    from app.trace.fastapi import TraceMiddleware
    app.add_middleware(TraceMiddleware)

The root span is named like the contract ("GET /api/data/sources/{sourceId}/stop"), so the dashboard
can line traces up with endpoints. A caller may send X-Trace-Id (e.g. the UI, to tie a click to the
backend work it caused); the response always carries it back. It may also send X-User-Action
("Clicked Place order") so the dashboard names the action by what the user did, not the endpoint.
"""
from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from . import TRACE_HEADER, span

ACTION_HEADER = "X-User-Action"
SKIP = ("/_viz", "/docs", "/openapi.json", "/redoc", "/favicon.ico")


_templates: list | None = None


def _route(request: Request):
    """The route template ('/api/v1/orders/{order_id}') and its path params, from the app's OpenAPI paths."""
    global _templates
    if _templates is None:
        _templates = []
        try:
            for path in (request.app.openapi().get("paths") or {}):
                rx = "^" + re.sub(r"\\\{([^}]+)\\\}", r"(?P<\1>[^/]+)", re.escape(path)) + "$"
                _templates.append((path, re.compile(rx)))
            _templates.sort(key=lambda t: t[0].count("{"))  # literal paths win over params
        except Exception:  # noqa: BLE001 - not FastAPI, or no OpenAPI
            pass
    for path, rx in _templates:
        m = rx.match(request.url.path)
        if m:
            return path, m.groupdict()
    return request.url.path, {}


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(SKIP):
            return await call_next(request)
        template, params = _route(request)
        with span(f"{request.method} {template}", trace_id=request.headers.get(TRACE_HEADER),
                  kind="request", method=request.method, route=template, path=request.url.path) as s:
            action = request.headers.get(ACTION_HEADER, "").strip()
            if action:
                s.attrs["action"] = action[:120]
            for key, value in params.items():
                s.tag(f"{key.removesuffix('Id').removesuffix('_id')}:{value}", "in")
            try:
                response = await call_next(request)
            except Exception:
                s.attrs["status"] = 500
                raise
            s.attrs["status"] = response.status_code
            response.headers[TRACE_HEADER] = s.trace
            return response
