"""Control: small, flat, well-factored code. Expect no findings and a score of 10."""

RATES = {"EU": 1.07, "US": 1.0}
DEFAULT_RATE = 1.1


def line_price(item, region):
    return item["price"] * RATES.get(region, DEFAULT_RATE)


def order_total(order, region):
    return sum(line_price(item, region) for item in order["items"])


def apply_coupon(total, coupon):
    if coupon == "HALF":
        return total / 2
    return total
