use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct Customer {
    pub id: u32,
    pub name: String,
}
