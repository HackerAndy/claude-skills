//! What `#[traced]` expands to. Not for use by hand.
//!
//! Arguments and results are described with "autoref specialisation": the call site borrows a `Probe`
//! several times, and method lookup picks the most specific impl the value's type allows (a `Result`
//! with `Debug` parts, anything `Debug`, then anything), all without nightly features.

use std::fmt::{Debug, Display};
use std::ops::Deref;
use std::path::Path;

pub use crate::{Instrumented, Outcome, Span, SpanSite, enabled, in_span};

const ARG_LIMIT: usize = 120;
const RESULT_LIMIT: usize = 160;
const REDACTED: &str = "‹redacted›";

/// Start the span for one call of a traced function.
pub fn start_call(name: Option<&str>, file: &'static str, here: &'static str, redact: Option<bool>) -> Span {
    if !enabled() {
        return Span(None);
    }
    let file = project_relative(file);
    let func = func_name(here);
    let redact = redact.unwrap_or_else(|| format!("/{file}").contains("/vault/"));
    Span::start(SpanSite { name: name.unwrap_or(&func), file: &file, func: &func, trace_id: None, redact })
}

/// Record an argument, or that it was redacted.
pub fn record_arg(span: &Span, name: &str, describe: &dyn Fn() -> String) {
    span.arg(name, describe());
}

/// Record that a secret-looking argument was passed, without its value.
pub fn record_secret(span: &Span, name: &str) {
    span.arg(name, REDACTED.to_owned());
}

/// Tag an `_id`/`_ids` argument's values as data ids of `kind`.
pub fn tag_ids(span: &Span, kind: &str, ids: Vec<String>) {
    for id in ids {
        span.tag(&format!("{kind}:{id}"), crate::Role::In);
    }
}

/// Ends a call's span: with its outcome when it returns, as failed when it panics or is dropped unfinished.
pub struct CallGuard<'a> {
    span: &'a Span,
    is_done: bool,
}

impl<'a> CallGuard<'a> {
    pub fn new(span: &'a Span) -> Self {
        Self { span, is_done: false }
    }

    pub fn finish(mut self, outcome: Outcome) {
        self.is_done = true;
        self.span.finish(outcome);
    }
}

impl Drop for CallGuard<'_> {
    fn drop(&mut self) {
        if !self.is_done {
            let why = if std::thread::panicking() { "panicked" } else { "cancelled" };
            self.span.finish(Outcome::failed(why));
        }
    }
}

fn project_relative(file: &str) -> String {
    let path = Path::new(file);
    if path.is_relative() {
        return file.to_owned();
    }
    let root = Path::new(crate::PROJECT_ROOT).canonicalize().unwrap_or_default();
    path.strip_prefix(&root).map_or_else(|_| file.to_owned(), |inside| inside.to_string_lossy().into_owned())
}

/// "Type.method" or "function", from the type name of an item declared inside the traced function:
/// `app::orders::OrderService::create::__bv_here`, `<app::Store as app::Port>::save::__bv_here`.
pub fn func_name(here: &str) -> String {
    let segments: Vec<&str> =
        split_path(here).into_iter().filter(|segment| *segment != "__bv_here" && !segment.starts_with('{')).collect();
    let Some((method, owners)) = segments.split_last() else {
        return here.to_owned();
    };
    match owners.last().map(|owner| owner_type(owner)) {
        Some(owner) if owner.starts_with(char::is_uppercase) => format!("{owner}.{method}"),
        _ => (*method).to_owned(),
    }
}

/// `<a::Store as b::Port>` -> `Store`; `Store<T>` -> `Store`.
fn owner_type(segment: &str) -> &str {
    let inner = segment.strip_prefix('<').and_then(|rest| rest.strip_suffix('>')).unwrap_or(segment);
    let self_type = inner.split(" as ").next().unwrap_or(inner);
    let last = split_path(self_type).last().copied().unwrap_or(self_type);
    last.split('<').next().unwrap_or(last)
}

/// Split on `::` outside angle brackets.
fn split_path(path: &str) -> Vec<&str> {
    let mut segments = Vec::new();
    let (mut depth, mut start) = (0_i32, 0);
    let bytes = path.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'<' => depth += 1,
            b'>' => depth -= 1,
            b':' if depth == 0 && bytes.get(index + 1) == Some(&b':') => {
                segments.push(&path[start..index]);
                index += 2;
                start = index;
                continue;
            }
            _ => {}
        }
        index += 1;
    }
    segments.push(&path[start..]);
    segments
}

fn short(text: String, limit: usize) -> String {
    if text.chars().count() <= limit {
        return text;
    }
    let mut cut: String = text.chars().take(limit - 1).collect();
    cut.push('…');
    cut
}

fn type_label<T: ?Sized>() -> String {
    let full = std::any::type_name::<T>();
    format!("<{}>", split_path(full).last().copied().unwrap_or(full))
}

fn describe_value(value: &dyn Debug, limit: usize) -> Option<String> {
    let text = format!("{value:?}");
    (text != "()").then(|| short(text, limit))
}

/// Borrowed several times at a call site so method lookup picks the most specific description.
pub struct Probe<'a, T: ?Sized>(pub &'a T);

/// The traits `#[traced]` calls through a [`Probe`]; glob-imported inside each traced body.
pub mod probes {
    use super::{Debug, Deref, Display, Outcome, Probe, RESULT_LIMIT, describe_value, type_label};

    pub trait DescribeDebug {
        fn describe(&self) -> String;
    }
    impl<T: Debug + ?Sized> DescribeDebug for &Probe<'_, T> {
        fn describe(&self) -> String {
            super::short(format!("{:?}", self.0), super::ARG_LIMIT)
        }
    }

    pub trait DescribeAny {
        fn describe(&self) -> String;
    }
    impl<T: ?Sized> DescribeAny for Probe<'_, T> {
        fn describe(&self) -> String {
            type_label::<T>()
        }
    }

    pub trait OutcomeResultDebug {
        fn outcome(&self) -> Outcome;
    }
    impl<T: Debug, E: Debug> OutcomeResultDebug for &&&Probe<'_, Result<T, E>> {
        fn outcome(&self) -> Outcome {
            match self.0 {
                Ok(value) => Outcome { ok: true, result: describe_value(value, RESULT_LIMIT), error: None },
                Err(error) => Outcome::failed(format!("{error:?}")),
            }
        }
    }

    pub trait OutcomeResult {
        fn outcome(&self) -> Outcome;
    }
    impl<T, E: Debug> OutcomeResult for &&Probe<'_, Result<T, E>> {
        fn outcome(&self) -> Outcome {
            match self.0 {
                Ok(_) => Outcome { ok: true, result: Some(type_label::<T>()), error: None },
                Err(error) => Outcome::failed(format!("{error:?}")),
            }
        }
    }

    pub trait OutcomeDebug {
        fn outcome(&self) -> Outcome;
    }
    impl<T: Debug> OutcomeDebug for &Probe<'_, T> {
        fn outcome(&self) -> Outcome {
            Outcome { ok: true, result: describe_value(self.0, RESULT_LIMIT), error: None }
        }
    }

    pub trait OutcomeAny {
        fn outcome(&self) -> Outcome;
    }
    impl<T> OutcomeAny for Probe<'_, T> {
        fn outcome(&self) -> Outcome {
            Outcome { ok: true, result: Some(type_label::<T>()), error: None }
        }
    }

    pub trait IdsText {
        fn ids(&self) -> Vec<String>;
    }
    impl<T: AsRef<str> + ?Sized> IdsText for &&&Probe<'_, T> {
        fn ids(&self) -> Vec<String> {
            vec![self.0.as_ref().to_owned()]
        }
    }

    pub trait IdsList {
        fn ids(&self) -> Vec<String>;
    }
    impl<T: Deref<Target = [S]>, S: AsRef<str>> IdsList for &&Probe<'_, T> {
        fn ids(&self) -> Vec<String> {
            self.0.iter().map(|id| id.as_ref().to_owned()).collect()
        }
    }

    pub trait IdsDisplay {
        fn ids(&self) -> Vec<String>;
    }
    impl<T: Display + ?Sized> IdsDisplay for &Probe<'_, T> {
        fn ids(&self) -> Vec<String> {
            vec![self.0.to_string()]
        }
    }

    pub trait IdsNone {
        fn ids(&self) -> Vec<String>;
    }
    impl<T: ?Sized> IdsNone for Probe<'_, T> {
        fn ids(&self) -> Vec<String> {
            Vec::new()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::func_name;

    #[test]
    fn names_methods_by_their_type_and_free_functions_alone() {
        assert_eq!(func_name("app::orders::OrderService::create::__bv_here"), "OrderService.create");
        assert_eq!(func_name("<app::store::Json as app::ports::Store>::save::__bv_here"), "Json.save");
        assert_eq!(func_name("app::store::Cache<T>::get::__bv_here"), "Cache.get");
        assert_eq!(func_name("app::orders::create_order::__bv_here"), "create_order");
    }
}
