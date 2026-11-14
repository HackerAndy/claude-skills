// Target smell: Excess Number of Function Arguments (5, &self included as CodeScene counts it).
pub struct Mailer;

impl Mailer {
    pub fn send(&self, to: &str, subject: &str, body: &str, cc: &str) -> String {
        format!("{to} {subject} {body} {cc}")
    }
}
