use axum::extract::Path;
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};

use crate::schemas::order::{Order, OrderIn};
use crate::services::order_service;

pub fn router() -> Router {
    Router::new()
        .route("/orders", get(list_orders).post(create_order))
        .route("/orders/{order_id}", get(get_order))
        .route("/orders/{order_id}/refund", post(refund)) // not in the contract
}

async fn list_orders() -> Json<Vec<Order>> {
    Json(order_service::list_orders())
}

async fn create_order(Json(body): Json<OrderIn>) -> Json<Order> {
    Json(order_service::create_order(body))
}

async fn get_order(Path(order_id): Path<u32>) -> Result<Json<Order>, StatusCode> {
    order_service::get_order(order_id).map(Json).map_err(|_| StatusCode::NOT_FOUND)
}

async fn refund(Path(order_id): Path<u32>) -> String {
    format!("refunded {order_id}")
}
