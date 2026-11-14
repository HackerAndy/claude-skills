// Target smell: Nested Complexity (depth 5; loops count). Cyclomatic complexity stays under 9.
pub struct Invoice { pub id: String, pub due: u64, pub paid: bool }
pub struct Account { pub active: bool, pub invoices: Vec<Invoice> }

pub fn find_overdue(accounts: &[Account], today: u64) -> Vec<String> {
    let mut overdue = Vec::new();
    for account in accounts {
        if account.active {
            for invoice in &account.invoices {
                if invoice.due < today {
                    if !invoice.paid {
                        overdue.push(invoice.id.clone());
                    }
                }
            }
        }
    }
    overdue
}
