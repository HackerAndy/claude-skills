use axum::extract::Path;
use axum::routing::get;
use axum::{Json, Router};

use crate::schemas::customer::Customer;
use crate::services::customer_service;

pub fn router() -> Router {
    Router::new().route("/customers/{customer_id}", get(get_customer))
}

async fn get_customer(Path(customer_id): Path<u32>) -> Json<Customer> {
    Json(customer_service::get_customer(customer_id))
}
