use crate::schemas::customer::Customer;

pub fn find(customer_id: u32) -> Customer {
    Customer { id: customer_id, name: format!("Customer {customer_id}") }
}
