//! `#[traced]` writes the same span records as the Python tracer.

use std::path::PathBuf;
use std::sync::OnceLock;

use trace::{Role, data, link, traced};

fn spans() -> Vec<String> {
    static OUT: OnceLock<PathBuf> = OnceLock::new();
    let path = OUT.get_or_init(|| {
        let path = std::env::temp_dir().join(format!("backend-viz-trace-test-{}.jsonl", std::process::id()));
        let _ = std::fs::remove_file(&path);
        trace::set_output(path.clone());
        path
    });
    std::fs::read_to_string(path).unwrap_or_default().lines().map(str::to_owned).collect()
}

fn span_of(func: &str) -> String {
    spans().into_iter().rev().find(|line| line.contains(&format!("\"func\": \"{func}\""))).expect("span written")
}

#[traced]
fn pull_payments(source_id: &str, limit: u32) -> Vec<String> {
    data(["payment:p1"], Role::Out);
    vec![format!("{source_id}-{limit}")]
}

#[test]
fn a_traced_function_records_args_result_and_data_ids() {
    spans();
    pull_payments("s1", 3);
    let line = spans().into_iter().find(|line| line.contains("source:s1")).expect("span written");
    assert!(line.contains("\"args\": {\"source_id\": \"\\\"s1\\\"\", \"limit\": \"3\"}"), "{line}");
    assert!(line.contains("{\"id\": \"source:s1\", \"role\": \"in\"}"), "{line}");
    assert!(line.contains("{\"id\": \"payment:p1\", \"role\": \"out\"}"), "{line}");
    assert!(line.contains("\"result\": \"[\\\"s1-3\\\"]\""), "{line}");
    assert!(line.contains("\"ok\": true"), "{line}");
    assert!(line.contains("\"file\": \"crates/trace/tests/traced.rs\"") || line.contains("\"file\": \"tests/traced.rs\""));
}

#[traced]
fn sign_in(user: &str, password: &str) -> usize {
    user.len() + password.len()
}

#[test]
fn secret_looking_args_are_redacted() {
    spans();
    sign_in("ana", "hunter2");
    let line = span_of("sign_in");
    assert!(line.contains("\"password\": \"‹redacted›\""), "{line}");
    assert!(!line.contains("hunter2"), "{line}");
}

#[derive(Debug)]
struct NotFound;

struct Organizer;

#[traced]
impl Organizer {
    pub fn tidy(&self, payment_id: &str) -> Result<String, NotFound> {
        if payment_id == "missing" {
            return Err(NotFound);
        }
        let row = format!("row:{payment_id}");
        link(&format!("payment:{payment_id}"), &row, "tidied");
        Ok(row)
    }

    fn private_helper(&self) -> u8 {
        1
    }
}

#[test]
fn methods_are_named_by_their_type_and_errors_fail_the_span() {
    spans();
    let organizer = Organizer;
    assert_eq!(organizer.private_helper(), 1);
    organizer.tidy("p7").expect("tidied");
    let line = span_of("Organizer.tidy");
    assert!(line.contains("{\"from\": \"payment:p7\", \"to\": \"row:p7\", \"how\": \"tidied\"}"), "{line}");
    assert!(organizer.tidy("missing").is_err());
    let failed = span_of("Organizer.tidy");
    assert!(failed.contains("\"ok\": false") && failed.contains("\"error\": \"NotFound\""), "{failed}");
    assert!(!spans().iter().any(|line| line.contains("private_helper")));
}

trait Store {
    fn save(&self, row_ids: Vec<String>) -> usize;
}

struct JsonStore;

#[traced]
impl Store for JsonStore {
    fn save(&self, row_ids: Vec<String>) -> usize {
        row_ids.len()
    }
}

#[test]
fn trait_impl_methods_are_traced_and_list_ids_tagged() {
    spans();
    JsonStore.save(vec!["r1".to_owned(), "r2".to_owned()]);
    let line = span_of("JsonStore.save");
    assert!(line.contains("{\"id\": \"row:r1\", \"role\": \"in\"}"), "{line}");
    assert!(line.contains("{\"id\": \"row:r2\", \"role\": \"in\"}"), "{line}");
}

#[traced]
async fn outer_job() -> Result<u8, String> {
    let inner = inner_step().await?;
    Ok(inner + 1)
}

#[traced]
async fn inner_step() -> Result<u8, String> {
    tokio::task::yield_now().await;
    Ok(1)
}

fn field<'a>(line: &'a str, key: &str) -> &'a str {
    let start = line.find(&format!("\"{key}\": ")).expect("field") + key.len() + 4;
    let rest = &line[start..];
    rest[..rest.find([',', '}']).expect("end")].trim_matches('"')
}

#[tokio::test]
async fn async_calls_nest_under_their_caller() {
    spans();
    assert_eq!(outer_job().await, Ok(2));
    let (outer, inner) = (span_of("outer_job"), span_of("inner_step"));
    assert_eq!(field(&inner, "parent"), field(&outer, "span"));
    assert_eq!(field(&inner, "trace"), field(&outer, "trace"));
}

#[test]
fn a_hand_opened_span_parents_the_calls_inside_it() {
    spans();
    let trace_id = trace::span("nightly pull", |opened| {
        pull_payments("s9", 1);
        opened.trace_id()
    });
    let line = spans().into_iter().find(|line| line.contains("source:s9")).expect("span written");
    assert_eq!(Some(field(&line, "trace").to_owned()), trace_id);
}
