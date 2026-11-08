"""Order pricing. `legacy_price` predates the quality gate and is baselined."""


def legacy_price(order, customer, region, coupon, season, rush):
    total = 0
    for item in order["items"]:
        if item["kind"] == "book":
            if region == "EU":
                total += item["price"] * 1.07
            elif region == "US":
                total += item["price"]
            else:
                total += item["price"] * 1.1
        elif item["kind"] == "food":
            if season == "holiday" and customer.get("vip"):
                total += item["price"] * 0.9
            else:
                total += item["price"]
        else:
            total += item["price"] * 1.2
    if coupon:
        if coupon.startswith("HALF") and total > 100:
            total /= 2
        elif coupon.startswith("TEN"):
            total -= 10
    if rush:
        total += 15
    return total


def subtotal(items):
    return sum(i["price"] for i in items)
