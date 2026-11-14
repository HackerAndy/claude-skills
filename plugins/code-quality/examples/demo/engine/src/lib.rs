pub struct Line {
    pub cents: u64,
    pub qty: u64,
}

pub fn subtotal_cents(lines: &[Line]) -> u64 {
    lines.iter().map(|l| l.cents * l.qty).sum()
}

pub fn legacy_rate(region: &str, member: bool, total: u64, coupon: Option<&str>) -> u64 {
    let mut rate = 100;
    if region == "EU" {
        if member {
            rate -= 10;
        }
    } else if region == "US" {
        if total > 10_000 && member {
            rate -= 5;
        }
    }
    match coupon {
        Some("HALF") => rate /= 2,
        Some(code) if code.starts_with("VIP") => rate -= 20,
        _ => {}
    }
    for step in [1_000, 5_000, 20_000] {
        if total > step {
            rate -= 1;
        }
    }
    while rate > 100 {
        rate -= 1;
    }
    rate
}
