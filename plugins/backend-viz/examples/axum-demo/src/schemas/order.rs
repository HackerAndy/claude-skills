use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize)]
pub struct Order {
    pub id: u32,
    pub sku: String,
    pub qty: u32,
    pub total: f64,
}

#[derive(Clone, Debug, Deserialize)]
pub struct OrderIn {
    pub sku: String,
    pub qty: u32,
    #[serde(skip)]
    pub total: Option<f64>,
}
