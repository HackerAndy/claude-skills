//! backend-viz runtime tracing: see every function that runs and follow data through the system.
//!
//! ```ignore
//! use trace::{traced, data, link, Role};
//!
//! #[traced]                                    // records each call as a span
//! pub fn organize(source_id: &str) { .. }      // args ending in _id/_ids are tagged as data automatically
//!
//! #[traced]
//! impl OrganizeService { .. }                  // traces every pub method (every method of a trait impl)
//!
//! data(["payment:p_123"], Role::Touch);        // tag the current span with a data id
//! link("payment:p_123", "row:r_9", "tidied");  // lineage: this data became that data (bronze -> silver)
//! ```
//!
//! Spans go to `.backend-viz/traces/spans.jsonl` (one JSON per line), the same records the Python tracer
//! writes, so the dashboard reads both. Secrets never get logged: args whose names look like secrets are
//! redacted, and every function in a file under a `vault` folder is recorded without args or results.
//! `BACKEND_VIZ_TRACE=0` switches tracing off, `=1` on; unset, it is on in debug builds only.
#![forbid(unsafe_code)]

use std::cell::RefCell;
use std::fs::{self, OpenOptions};
use std::future::Future;
use std::io::Write as _;
use std::path::PathBuf;
use std::pin::Pin;
use std::sync::{Arc, Mutex, OnceLock, PoisonError, RwLock};
use std::task::{Context, Poll};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub use trace_macros::traced;

#[doc(hidden)]
pub mod __private;
#[cfg(feature = "axum")]
pub mod axum;
mod ids;
mod record;

/// The request header a caller may send to tie its requests into one trace; responses carry it back.
pub const TRACE_HEADER: &str = "X-Trace-Id";
/// The request header naming what the user did ("Clicked Place order"), shown instead of the endpoint.
pub const ACTION_HEADER: &str = "X-User-Action";

const MAX_BYTES: u64 = 20 * 1024 * 1024;
const PROJECT_ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../.."); // <project>/crates/trace -> <project>

thread_local! {
    static CURRENT: RefCell<Option<Span>> = const { RefCell::new(None) };
}

static OUTPUT: RwLock<Option<PathBuf>> = RwLock::new(None);
static WRITE: Mutex<()> = Mutex::new(());

/// How a data id took part in a call.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    In,
    Out,
    Touch,
}

impl Role {
    fn as_str(self) -> &'static str {
        match self {
            Self::In => "in",
            Self::Out => "out",
            Self::Touch => "touch",
        }
    }
}

/// A value on a span's `attrs`.
#[derive(Clone, Debug)]
pub enum Attr {
    Text(String),
    Number(i64),
}

/// How a span ended: ok or not, and a short result or error.
#[derive(Clone, Debug, Default)]
pub struct Outcome {
    pub ok: bool,
    pub result: Option<String>,
    pub error: Option<String>,
}

impl Outcome {
    /// Ended normally with nothing to show.
    pub fn ok() -> Self {
        Self { ok: true, result: None, error: None }
    }

    /// Ended with an error.
    pub fn failed(error: impl Into<String>) -> Self {
        Self { ok: false, result: None, error: Some(error.into()) }
    }
}

struct SpanState {
    trace: String,
    id: String,
    parent: Option<String>,
    name: String,
    file: String,
    func: String,
    start_ms: f64,
    started: Instant,
    args: Vec<(String, String)>,
    data: Vec<(String, Role)>,
    links: Vec<(String, String, String)>,
    attrs: Vec<(String, Attr)>,
    redact: bool,
    finished: bool,
}

/// One timed piece of work. Cheap to clone; a no-op while tracing is off.
#[derive(Clone)]
pub struct Span(Option<Arc<Mutex<SpanState>>>);

/// Where a span is in the code. `file` and `func` are empty for spans opened by hand.
#[derive(Clone, Copy, Debug, Default)]
pub struct SpanSite<'a> {
    pub name: &'a str,
    pub file: &'a str,
    pub func: &'a str,
    pub trace_id: Option<&'a str>,
    pub redact: bool,
}

impl Span {
    /// Start a span under the current one (same trace), or a new trace when there is none or `trace_id` differs.
    pub fn start(site: SpanSite<'_>) -> Self {
        if !enabled() {
            return Self(None);
        }
        let parent = current();
        let parent_ids = parent.as_ref().and_then(Span::ids);
        let trace = site
            .trace_id
            .map(str::to_owned)
            .or_else(|| parent_ids.as_ref().map(|(trace, _)| trace.clone()))
            .unwrap_or_else(|| ids::random_hex(16));
        let parent_id = parent_ids.filter(|(parent_trace, _)| *parent_trace == trace).map(|(_, id)| id);
        Self(Some(Arc::new(Mutex::new(SpanState {
            trace,
            id: ids::random_hex(12),
            parent: parent_id,
            name: site.name.to_owned(),
            file: site.file.to_owned(),
            func: site.func.to_owned(),
            start_ms: epoch_ms(),
            started: Instant::now(),
            args: Vec::new(),
            data: Vec::new(),
            links: Vec::new(),
            attrs: Vec::new(),
            redact: site.redact,
            finished: false,
        }))))
    }

    fn with_state<R>(&self, update: impl FnOnce(&mut SpanState) -> R) -> Option<R> {
        let shared = self.0.as_ref()?;
        let mut state = shared.lock().unwrap_or_else(PoisonError::into_inner);
        Some(update(&mut state))
    }

    fn ids(&self) -> Option<(String, String)> {
        self.with_state(|state| (state.trace.clone(), state.id.clone()))
    }

    /// The trace this span belongs to, while tracing is on.
    pub fn trace_id(&self) -> Option<String> {
        self.with_state(|state| state.trace.clone())
    }

    /// Tag this span with a data id ("payment:p_1"), once per id and role.
    pub fn tag(&self, id: &str, role: Role) {
        self.with_state(|state| {
            if !state.data.iter().any(|(known, known_role)| known == id && *known_role == role) {
                state.data.push((id.to_owned(), role));
            }
        });
    }

    /// Record an argument's short description.
    pub fn arg(&self, name: &str, description: String) {
        self.with_state(|state| state.args.push((name.to_owned(), description)));
    }

    /// Set an attribute (`kind`, `status`, `route`…).
    pub fn attr(&self, key: &str, value: Attr) {
        self.with_state(|state| {
            state.attrs.retain(|(known, _)| known != key);
            state.attrs.push((key.to_owned(), value));
        });
    }

    /// Lineage on this span: `source` became (or fed) `target`.
    pub fn link(&self, source: &str, target: &str, how: &str) {
        self.with_state(|state| state.links.push((source.to_owned(), target.to_owned(), how.to_owned())));
        self.tag(source, Role::In);
        self.tag(target, Role::Out);
    }

    /// End the span and append its record. Only the first call counts.
    pub fn finish(&self, outcome: Outcome) {
        let line = self.with_state(|state| {
            if state.finished {
                return None;
            }
            state.finished = true;
            let ms = state.started.elapsed().as_secs_f64() * 1000.0;
            Some(record::line(&record::Record { state, ms, outcome: &outcome }))
        });
        if let Some(Some(line)) = line {
            append(&line);
        }
    }
}

/// Runs `work` with `span` as the current span, so calls inside it nest under it.
pub fn in_span<R>(span: &Span, work: impl FnOnce() -> R) -> R {
    let previous = CURRENT.with(|current| current.replace(Some(span.clone())));
    let _restore = Restore(previous);
    work()
}

struct Restore(Option<Span>);

impl Drop for Restore {
    fn drop(&mut self) {
        let previous = self.0.take();
        CURRENT.with(|current| *current.borrow_mut() = previous);
    }
}

/// A future that runs with its span as the current span on every poll, on whatever thread polls it.
pub struct Instrumented<F> {
    span: Span,
    inner: Pin<Box<F>>,
}

impl<F: Future> Instrumented<F> {
    /// Wrap `future` so the work it does lands under `span`.
    pub fn new(span: Span, future: F) -> Self {
        Self { span, inner: Box::pin(future) }
    }
}

impl<F: Future> Future for Instrumented<F> {
    type Output = F::Output;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<F::Output> {
        let this = self.get_mut();
        in_span(&this.span, || this.inner.as_mut().poll(context))
    }
}

/// A span you open by hand: a scheduled job, an event handler, a pipeline run. Ends ok when `work` returns.
pub fn span<R>(name: &str, work: impl FnOnce(&Span) -> R) -> R {
    let opened = Span::start(SpanSite { name, ..SpanSite::default() });
    let guard = __private::CallGuard::new(&opened);
    let result = in_span(&opened, || work(&opened));
    guard.finish(Outcome::ok());
    result
}

/// The async form of [`span`]: runs `future` under `opened`, then ends it ok.
pub async fn span_async<F: Future>(opened: Span, future: F) -> F::Output {
    let guard = __private::CallGuard::new(&opened);
    let result = Instrumented::new(opened.clone(), future).await;
    guard.finish(Outcome::ok());
    result
}

/// What a request-shaped span is: from HTTP, or from a desktop command standing in for a contract route.
#[derive(Clone, Copy, Debug)]
pub struct RequestInfo<'a> {
    pub method: &'a str,
    /// The route as the contract writes it: `/api/data/sources/{sourceId}/stop`.
    pub route: &'a str,
    pub path: &'a str,
    pub trace_id: Option<&'a str>,
    pub action: Option<&'a str>,
}

const ACTION_LIMIT: usize = 120;

/// Open the root span of one request, named like the contract ("GET /api/data/sources/{sourceId}/stop") so the
/// dashboard can line traces up with endpoints. Path params are tagged as data (`sourceId` -> `source:`).
pub fn request_span(request: RequestInfo<'_>) -> Span {
    let name = format!("{} {}", request.method, request.route);
    let opened = Span::start(SpanSite { name: &name, trace_id: request.trace_id, ..SpanSite::default() });
    opened.attr("kind", Attr::Text("request".to_owned()));
    opened.attr("method", Attr::Text(request.method.to_owned()));
    opened.attr("route", Attr::Text(request.route.to_owned()));
    opened.attr("path", Attr::Text(request.path.to_owned()));
    if let Some(action) = request.action.map(str::trim).filter(|action| !action.is_empty()) {
        opened.attr("action", Attr::Text(action.chars().take(ACTION_LIMIT).collect()));
    }
    for (param, value) in path_params(request.route, request.path) {
        let kind = param.strip_suffix("Id").unwrap_or(param);
        let kind = kind.strip_suffix("_id").unwrap_or(kind);
        opened.tag(&format!("{kind}:{value}"), Role::In);
    }
    opened
}

fn path_params<'a>(route: &'a str, path: &'a str) -> Vec<(&'a str, &'a str)> {
    route
        .split('/')
        .zip(path.split('/'))
        .filter_map(|(part, value)| Some((part.strip_prefix('{')?.strip_suffix('}')?, value)))
        .collect()
}

fn current() -> Option<Span> {
    CURRENT.with(|current| current.borrow().clone())
}

/// The trace the running code belongs to, if any.
pub fn current_trace_id() -> Option<String> {
    current().and_then(|span| span.trace_id())
}

/// Tag the running span with data ids ("payment:p_1").
pub fn data<S: AsRef<str>>(ids: impl IntoIterator<Item = S>, role: Role) {
    if let Some(span) = current() {
        for id in ids {
            span.tag(id.as_ref(), role);
        }
    }
}

/// Lineage: `source` became (or fed) `target`, e.g. `link("payment:p1", "row:r1", "tidied")`.
pub fn link(source: &str, target: &str, how: &str) {
    if let Some(span) = current() {
        span.link(source, target, how);
    }
}

/// Write spans somewhere else (a desktop app's data folder, a test's temp file). Call once at startup.
pub fn set_output(path: PathBuf) {
    *OUTPUT.write().unwrap_or_else(PoisonError::into_inner) = Some(path);
}

/// Whether spans are being recorded.
pub fn enabled() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| match std::env::var("BACKEND_VIZ_TRACE").as_deref() {
        Ok("0") => false,
        Ok(_) => true,
        Err(_) => cfg!(debug_assertions),
    })
}

fn output() -> PathBuf {
    if let Some(path) = OUTPUT.read().unwrap_or_else(PoisonError::into_inner).clone() {
        return path;
    }
    std::env::var_os("BACKEND_VIZ_TRACE_FILE").map_or_else(
        || PathBuf::from(PROJECT_ROOT).join(".backend-viz").join("traces").join("spans.jsonl"),
        PathBuf::from,
    )
}

/// Tracing must never break the app, so a span that can't be written is dropped.
fn append(line: &str) {
    let _serial = WRITE.lock().unwrap_or_else(PoisonError::into_inner);
    let path = output();
    if let Some(folder) = path.parent()
        && fs::create_dir_all(folder).is_err()
    {
        return;
    }
    if fs::metadata(&path).is_ok_and(|meta| meta.len() > MAX_BYTES) {
        let _ignored = fs::rename(&path, path.with_extension("jsonl.1"));
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&path) {
        let _ignored = file.write_all(line.as_bytes());
    }
}

fn epoch_ms() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map_or(0.0, |since| since.as_secs_f64() * 1000.0)
}
