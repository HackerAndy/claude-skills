use crate::repositories::customer_repo;
use crate::schemas::customer::Customer;

pub fn get_customer(customer_id: u32) -> Customer {
    customer_repo::find(customer_id)
}
