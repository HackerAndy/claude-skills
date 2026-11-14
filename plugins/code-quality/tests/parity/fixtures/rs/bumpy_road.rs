// Target smell: Bumpy Road (3 bumps, each nested 2 deep). Nesting and CC stay low.
pub struct Contact { pub name: Option<String>, pub email: Option<String>, pub phone: Option<String>, pub seen: bool, pub checked: bool }

pub fn normalise(mut record: Contact) -> Contact {
    if let Some(name) = &record.name {
        if *name == name.to_uppercase() {
            record.name = Some(name.to_lowercase());
        }
    }
    record.seen = true;
    if let Some(email) = &record.email {
        if email.contains(' ') {
            record.email = Some(email.trim().to_string());
        }
    }
    record.checked = true;
    if let Some(phone) = &record.phone {
        if phone.starts_with("00") {
            record.phone = Some(format!("+{}", &phone[2..]));
        }
    }
    record
}
