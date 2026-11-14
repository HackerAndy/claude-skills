pub mod customers;
pub mod orders;

use axum::Router;

pub fn api() -> Router {
    Router::new().merge(orders::router()).merge(customers::router())
}
