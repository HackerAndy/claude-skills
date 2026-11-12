"""Target smell: Complex Conditional (one condition with 4 clauses). Nothing else."""


def can_ship(order):
    if order["paid"] and order["address"] and not order["on_hold"] or order["override"]:
        return True
    return False
