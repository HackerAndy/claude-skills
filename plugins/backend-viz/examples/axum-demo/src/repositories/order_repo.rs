use std::sync::Mutex;

use trace::{Role, data, traced};

use crate::schemas::order::{Order, OrderIn};

static ORDERS: Mutex<Vec<Order>> = Mutex::new(Vec::new());

#[traced]
pub fn all() -> Vec<Order> {
    let orders = ORDERS.lock().expect("orders").clone();
    data(orders.iter().map(|order| format!("order:{}", order.id)), Role::Out);
    orders
}

#[traced]
pub fn get(order_id: u32) -> Option<Order> {
    ORDERS.lock().expect("orders").iter().find(|order| order.id == order_id).cloned()
}

#[traced]
pub fn insert(body: OrderIn) -> Order {
    let mut orders = ORDERS.lock().expect("orders");
    let id = u32::try_from(orders.len()).expect("fits") + 1;
    let order = Order { id, sku: body.sku, qty: body.qty, total: body.total.unwrap_or_default() };
    orders.push(order.clone());
    data([format!("order:{id}")], Role::Out);
    order
}
