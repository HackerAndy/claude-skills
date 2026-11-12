"""Target smell: Nested Complexity (depth 4). Cyclomatic complexity stays under 9."""


def find_overdue(accounts, today):
    overdue = []
    for account in accounts:
        if account["active"]:
            for invoice in account["invoices"]:
                if invoice["due"] < today:
                    if not invoice["paid"]:
                        overdue.append(invoice["id"])
    return overdue
