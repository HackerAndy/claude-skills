// Target smell: Complex Conditional (one condition with 4 clauses). Nothing else.
pub struct Order { pub paid: bool, pub address: String, pub on_hold: bool, pub override_hold: bool }

pub fn can_ship(order: &Order) -> bool {
    if (order.paid && !order.address.is_empty() && !order.on_hold) || order.override_hold {
        return true;
    }
    false
}
