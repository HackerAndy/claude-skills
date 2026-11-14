// Control: small, flat, well-factored code. Expect no findings and a score of 10.
pub struct Item { pub price: f64 }

const DEFAULT_RATE: f64 = 1.1;

fn rate(region: &str) -> f64 {
    match region { "EU" => 1.07, "US" => 1.0, _ => DEFAULT_RATE }
}

pub fn line_price(item: &Item, region: &str) -> f64 {
    item.price * rate(region)
}

pub fn order_total(items: &[Item], region: &str) -> f64 {
    items.iter().map(|item| line_price(item, region)).sum()
}
