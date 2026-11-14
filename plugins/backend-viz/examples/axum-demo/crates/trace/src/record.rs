//! One span as a line of JSON, in the same shape as the Python tracer's records.

use std::fmt::Write as _;

use crate::{Attr, Outcome, SpanState};

pub(crate) struct Record<'a> {
    pub state: &'a SpanState,
    pub ms: f64,
    pub outcome: &'a Outcome,
}

pub(crate) fn line(record: &Record<'_>) -> String {
    let state = record.state;
    let null = || "null".to_owned();
    let result = if state.redact { None } else { record.outcome.result.as_deref() };
    let fields = [
        ("trace", text(&state.trace)),
        ("span", text(&state.id)),
        ("parent", state.parent.as_deref().map_or_else(null, text)),
        ("name", text(&state.name)),
        ("file", text(&state.file)),
        ("func", text(&state.func)),
        ("start", format!("{:.3}", state.start_ms)),
        ("ms", format!("{:.3}", record.ms)),
        ("ok", record.outcome.ok.to_string()),
        ("args", object(if state.redact { &[] } else { &state.args })),
        ("result", result.map_or_else(null, text)),
        ("error", record.outcome.error.as_deref().map_or_else(null, text)),
        ("data", data(state)),
        ("links", links(state)),
        ("attrs", attrs(state)),
    ];
    let inner: Vec<String> = fields.iter().map(|(key, json)| format!("{}: {json}", text(key))).collect();
    format!("{{{}}}\n", inner.join(", "))
}

fn object(pairs: &[(String, String)]) -> String {
    let inner: Vec<String> = pairs.iter().map(|(key, value)| format!("{}: {}", text(key), text(value))).collect();
    format!("{{{}}}", inner.join(", "))
}

fn data(state: &SpanState) -> String {
    let items: Vec<String> = state
        .data
        .iter()
        .map(|(id, role)| format!("{{\"id\": {}, \"role\": {}}}", text(id), text(role.as_str())))
        .collect();
    format!("[{}]", items.join(", "))
}

fn links(state: &SpanState) -> String {
    let items: Vec<String> = state
        .links
        .iter()
        .map(|(from, to, how)| format!("{{\"from\": {}, \"to\": {}, \"how\": {}}}", text(from), text(to), text(how)))
        .collect();
    format!("[{}]", items.join(", "))
}

fn attrs(state: &SpanState) -> String {
    let items: Vec<String> = state
        .attrs
        .iter()
        .map(|(key, value)| match value {
            Attr::Text(value) => format!("{}: {}", text(key), text(value)),
            Attr::Number(value) => format!("{}: {value}", text(key)),
        })
        .collect();
    format!("{{{}}}", items.join(", "))
}

/// A JSON string literal.
pub(crate) fn text(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');
    for character in value.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            control if u32::from(control) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", u32::from(control));
            }
            other => out.push(other),
        }
    }
    out.push('"');
    out
}

#[cfg(test)]
mod tests {
    use super::text;

    #[test]
    fn escapes_quotes_backslashes_and_control_characters() {
        assert_eq!(text("a\"b\\c\nd\u{1}"), "\"a\\\"b\\\\c\\nd\\u0001\"");
    }
}
