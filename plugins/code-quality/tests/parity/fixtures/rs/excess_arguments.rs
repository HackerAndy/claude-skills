// Target smell: Excess Number of Function Arguments (6). Body is trivial.
pub struct User { pub name: String, pub email: String, pub role: String, pub team: String, pub tz: String, pub locale: String }

pub fn create_user(name: String, email: String, role: String, team: String, timezone: String, locale: String) -> User {
    User { name, email, role, team, tz: timezone, locale }
}
