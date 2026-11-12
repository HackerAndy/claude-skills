"""Target smell: Code Duplication (two near-identical functions of about 20 lines each)."""


def summarise_orders(orders, currency):
    total = 0
    count = 0
    largest = None
    smallest = None
    skipped = []
    for order in orders:
        if order["status"] == "cancelled":
            skipped.append(order["id"])
            continue
        amount = order["amount"] if order["currency"] == currency else order["amount"] * order["rate"]
        total += amount
        count += 1
        if largest is None or amount > largest:
            largest = amount
        if smallest is None or amount < smallest:
            smallest = amount
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average, "largest": largest,
            "smallest": smallest, "skipped": skipped}


def summarise_refunds(refunds, currency):
    total = 0
    count = 0
    largest = None
    smallest = None
    skipped = []
    for refund in refunds:
        if refund["status"] == "cancelled":
            skipped.append(refund["id"])
            continue
        amount = refund["amount"] if refund["currency"] == currency else refund["amount"] * refund["rate"]
        total += amount
        count += 1
        if largest is None or amount > largest:
            largest = amount
        if smallest is None or amount < smallest:
            smallest = amount
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average, "largest": largest,
            "smallest": smallest, "skipped": skipped}
