"""
backend-viz runtime tracing: see every function that runs and follow data through the system.

    from app.trace import traced, data, link

    @traced                                  # records each call as a span
    def organize(source_id: str): ...        # args ending in _id/_ids are tagged as data automatically

    @traced
    class OrganizeService: ...               # traces every public method

    data("payment:p_123")                    # tag the current span with a data id
    link("payment:p_123", "row:r_9")         # lineage: this data became that data (bronze -> silver)

Spans go to .backend-viz/traces/spans.jsonl (one JSON per line). backend-viz draws them as
waterfalls and data journeys; the field names follow OpenTelemetry so they can be exported later.

Secrets never get logged: args/results whose names look like secrets are redacted, and every
function in a module under a `vault` package is recorded without args or results.
Set BACKEND_VIZ_TRACE=0 to switch tracing off.
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar, overload

__all__ = ["traced", "data", "link", "span", "current_trace_id", "TRACE_HEADER"]

TRACE_HEADER = "X-Trace-Id"
ENABLED = os.environ.get("BACKEND_VIZ_TRACE", "1") != "0"
_ROOT = Path(__file__).resolve().parents[2]  # <project>/app/trace/__init__.py -> <project>
OUT = Path(os.environ.get("BACKEND_VIZ_TRACE_FILE") or _ROOT / ".backend-viz" / "traces" / "spans.jsonl")
MAX_BYTES = 20 * 1024 * 1024
SECRET = re.compile(r"pass(word)?|secret|token|api_?key|credential|auth|cookie|session_key", re.I)
DATA_ARG = re.compile(r"(^id$|_id$|_ids$|^ids$)")

_current: contextvars.ContextVar["_Span | None"] = contextvars.ContextVar("backend_viz_span", default=None)
_lock = threading.Lock()
_Traced = TypeVar("_Traced")


def _short(value: Any, limit: int = 160) -> str:
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001
        text = f"<{type(value).__name__}>"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _code_of(fn: Callable) -> tuple[str, str]:
    """('app/services/data.py', 'DataService.get_state') relative to the project."""
    try:
        file = Path(inspect.getsourcefile(fn) or "").resolve()
        rel = file.relative_to(_ROOT).as_posix()
    except (TypeError, ValueError):
        rel = getattr(fn, "__module__", "?").replace(".", "/") + ".py"
    return rel, fn.__qualname__


class _Span:
    __slots__ = ("trace", "id", "parent", "name", "file", "func", "start", "args", "data", "links", "attrs", "redact")

    def __init__(self, name: str, file: str = "", func: str = "", trace: str | None = None, redact: bool = False):
        parent = _current.get()
        self.trace = trace or (parent.trace if parent else uuid.uuid4().hex[:16])
        self.id = uuid.uuid4().hex[:12]
        self.parent = parent.id if parent and parent.trace == self.trace else None
        self.name, self.file, self.func, self.redact = name, file, func, redact
        self.start = time.time()
        self.args: dict[str, str] = {}
        self.data: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.attrs: dict[str, Any] = {}

    def tag(self, ident: str, role: str) -> None:
        if not any(d["id"] == ident and d["role"] == role for d in self.data):
            self.data.append({"id": ident, "role": role})

    def finish(self, ok: bool, result: Any = None, error: BaseException | None = None) -> None:
        if not ENABLED:
            return
        rec = {
            "trace": self.trace, "span": self.id, "parent": self.parent, "name": self.name,
            "file": self.file, "func": self.func, "start": round(self.start * 1000, 3),
            "ms": round((time.time() - self.start) * 1000, 3), "ok": ok,
            "args": {} if self.redact else self.args,
            "result": None if self.redact or result is None else _short(result),
            "error": f"{type(error).__name__}: {error}" if error else None,
            "data": self.data, "links": self.links, "attrs": self.attrs,
        }
        line = json.dumps(rec, default=str) + "\n"
        with _lock:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            try:
                if OUT.exists() and OUT.stat().st_size > MAX_BYTES:
                    OUT.replace(OUT.with_suffix(".jsonl.1"))
            except OSError:
                pass
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(line)


@contextmanager
def span(name: str, *, trace_id: str | None = None, **attrs: Any) -> Iterator[_Span]:
    """A span you open by hand: a request, a scheduled job, an event handler, a pipeline run."""
    s = _Span(name, trace=trace_id)
    s.attrs.update(attrs)
    token = _current.set(s)
    try:
        yield s
    except BaseException as exc:
        s.finish(False, error=exc)
        raise
    else:
        s.finish(True)
    finally:
        _current.reset(token)


def current_trace_id() -> str | None:
    s = _current.get()
    return s.trace if s else None


def data(*ids: str, role: str = "touch") -> None:
    """Tag the running span with data ids ('payment:p_1'). role: in | out | touch."""
    s = _current.get()
    if s:
        for i in ids:
            s.tag(str(i), role)


def link(source: str, target: str, how: str = "") -> None:
    """Lineage: `source` became (or fed) `target`, e.g. link('payment:p1', 'row:r1', 'tidied')."""
    s = _current.get()
    if s:
        s.links.append({"from": str(source), "to": str(target), "how": how})
        s.tag(str(source), "in")
        s.tag(str(target), "out")


def _bind(fn: Callable, s: _Span, args: tuple, kwargs: dict) -> None:
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        return
    for name, value in bound.arguments.items():
        if name in ("self", "cls"):
            continue
        if SECRET.search(name):
            s.args[name] = "‹redacted›"
            continue
        s.args[name] = _short(value, 120)
        if DATA_ARG.search(name):
            values = value if isinstance(value, (list, tuple, set)) else [value]
            for v in values:
                if isinstance(v, (str, int)):
                    s.tag(f"{name.removesuffix('s').removesuffix('_id')}:{v}", "in")


@overload
def traced(target: _Traced) -> _Traced: ...
@overload
def traced(*, name: str | None = None, redact: bool | None = None) -> Callable[[_Traced], _Traced]: ...


def traced(target: Any = None, *, name: str | None = None, redact: bool | None = None) -> Any:
    """Decorate a function or a class (every public method) so each call becomes a span."""

    def wrap_fn(fn: Callable) -> Callable:
        if getattr(fn, "__backend_viz_traced__", False):
            return fn
        file, func = _code_of(fn)
        hide = redact if redact is not None else ("/vault/" in f"/{file}")
        label = name or func

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                s = _Span(label, file, func, redact=hide)
                _bind(fn, s, args, kwargs)
                token = _current.set(s)
                try:
                    result = await fn(*args, **kwargs)
                except BaseException as exc:
                    s.finish(False, error=exc)
                    raise
                finally:
                    _current.reset(token)
                s.finish(True, result)
                return result
            wrapper: Callable = awrapper
        else:
            @functools.wraps(fn)
            def swrapper(*args, **kwargs):
                s = _Span(label, file, func, redact=hide)
                _bind(fn, s, args, kwargs)
                token = _current.set(s)
                try:
                    result = fn(*args, **kwargs)
                except BaseException as exc:
                    s.finish(False, error=exc)
                    raise
                finally:
                    _current.reset(token)
                s.finish(True, result)
                return result
            wrapper = swrapper
        wrapper.__backend_viz_traced__ = True  # type: ignore[attr-defined]
        return wrapper

    def wrap_cls(cls: type) -> type:
        for attr, value in list(vars(cls).items()):
            if attr.startswith("_"):
                continue
            if isinstance(value, staticmethod):
                setattr(cls, attr, staticmethod(wrap_fn(value.__func__)))
            elif isinstance(value, classmethod):
                setattr(cls, attr, classmethod(wrap_fn(value.__func__)))
            elif inspect.isfunction(value):
                setattr(cls, attr, wrap_fn(value))
        return cls

    def apply(obj: Any):
        return wrap_cls(obj) if inspect.isclass(obj) else wrap_fn(obj)

    return apply(target) if target is not None else apply
