//! One trace per HTTP request, for axum. Add once where the router is built:
//!
//! ```ignore
//! let app = Router::new() /* routes */ .layer(axum::middleware::from_fn(trace::axum::trace_request));
//! ```
//!
//! The root span is named like the contract ("GET /api/data/sources/{sourceId}/stop"), from axum's matched
//! route. A caller may send `X-Trace-Id` (e.g. the UI, to tie a click to the work it caused); the response
//! always carries it back. It may also send `X-User-Action` so the dashboard names the action by what the
//! user did.

use axum::extract::{MatchedPath, Request};
use axum::http::HeaderValue;
use axum::middleware::Next;
use axum::response::Response;

use crate::{ACTION_HEADER, Attr, Instrumented, Outcome, RequestInfo, TRACE_HEADER, request_span};

const SKIP: &[&str] = &["/_viz", "/docs", "/openapi.json", "/redoc", "/favicon.ico"];

/// axum middleware (`axum::middleware::from_fn`): runs the request under a request span.
pub async fn trace_request(request: Request, next: Next) -> Response {
    let path = request.uri().path().to_owned();
    if SKIP.iter().any(|skipped| path.starts_with(skipped)) {
        return next.run(request).await;
    }
    let method = request.method().as_str().to_owned();
    let route = request.extensions().get::<MatchedPath>().map_or_else(|| path.clone(), |m| m.as_str().to_owned());
    let (trace_id, action) = (header(&request, TRACE_HEADER), header(&request, ACTION_HEADER));
    let span = request_span(RequestInfo {
        method: &method,
        route: &route,
        path: &path,
        trace_id: trace_id.as_deref(),
        action: action.as_deref(),
    });
    let mut response = Instrumented::new(span.clone(), next.run(request)).await;
    span.attr("status", Attr::Number(i64::from(response.status().as_u16())));
    if let Some(value) = span.trace_id().and_then(|trace| HeaderValue::from_str(&trace).ok()) {
        response.headers_mut().insert(TRACE_HEADER, value);
    }
    span.finish(Outcome::ok());
    response
}

fn header(request: &Request, name: &str) -> Option<String> {
    request.headers().get(name).and_then(|value| value.to_str().ok()).map(str::to_owned)
}
