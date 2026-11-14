use trace::{link, traced};

use crate::repositories::order_repo;
use crate::schemas::order::{Order, OrderIn};

#[derive(Debug)]
pub struct NotFound;

const UNIT_PRICE: f64 = 9.99;

#[traced]
pub fn list_orders() -> Vec<Order> {
    order_repo::all()
}

#[traced]
pub fn create_order(body: OrderIn) -> Order {
    let draft = format!("draft:{}-{}", body.sku, body.qty);
    let order = order_repo::insert(price(body));
    link(&draft, &format!("order:{}", order.id), "saved"); // lineage: the request became order N
    order
}

#[traced]
pub fn price(body: OrderIn) -> OrderIn {
    OrderIn { total: Some(f64::from(body.qty) * UNIT_PRICE), ..body }
}

#[traced]
pub fn get_order(order_id: u32) -> Result<Order, NotFound> {
    order_repo::get(order_id).ok_or(NotFound)
}
