mod core;
mod repositories;
mod routes;
mod schemas;
mod services;

use axum::Router;
use axum::routing::get;

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/health", get(health))
        .nest("/api/v1", routes::api())
        .layer(axum::middleware::from_fn(trace::axum::trace_request));
    let listener = tokio::net::TcpListener::bind(core::config::ADDRESS).await.expect("port is free");
    axum::serve(listener, app).await.expect("server runs");
}

async fn health() -> &'static str {
    "ok"
}
