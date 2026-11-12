"""Target smell: Brain Method (large, complex, deeply nested, central to the file)."""


def process_batch(batch, rules, ledger):
    results = []
    errors = []
    for entry in batch:
        kind = entry.get("kind")
        amount = entry.get("amount", 0)
        if kind == "credit":
            if amount > 0:
                for rule in rules:
                    if rule["applies_to"] == "credit":
                        if rule["min"] <= amount <= rule["max"]:
                            amount = amount * rule["factor"]
                ledger["credits"] += amount
                results.append(("credit", entry["id"], amount))
            else:
                errors.append((entry["id"], "credit must be positive"))
        elif kind == "debit":
            if amount > 0:
                if ledger["balance"] - amount < 0:
                    if entry.get("allow_overdraft"):
                        ledger["overdrafts"] += 1
                    else:
                        errors.append((entry["id"], "insufficient funds"))
                        continue
                ledger["debits"] += amount
                ledger["balance"] -= amount
                results.append(("debit", entry["id"], amount))
            else:
                errors.append((entry["id"], "debit must be positive"))
        elif kind == "transfer":
            target = entry.get("target")
            if not target:
                errors.append((entry["id"], "transfer needs a target"))
            elif target == entry.get("source"):
                errors.append((entry["id"], "transfer to self"))
            else:
                for rule in rules:
                    if rule["applies_to"] == "transfer" and amount > rule["max"]:
                        errors.append((entry["id"], "transfer over limit"))
                        break
                else:
                    ledger["transfers"] += amount
                    results.append(("transfer", entry["id"], amount))
        elif kind == "fee":
            ledger["fees"] += amount
            ledger["balance"] -= amount
            results.append(("fee", entry["id"], amount))
        elif kind == "interest":
            rate = entry.get("rate", 0)
            if rate > 0.2:
                errors.append((entry["id"], "rate too high"))
            else:
                interest = ledger["balance"] * rate
                ledger["balance"] += interest
                results.append(("interest", entry["id"], interest))
        else:
            errors.append((entry["id"], "unknown kind"))
    if errors and not results:
        ledger["failed_batches"] += 1
    elif errors:
        ledger["partial_batches"] += 1
    else:
        ledger["clean_batches"] += 1
    summary = {"ok": len(results), "failed": len(errors), "balance": ledger["balance"]}
    if summary["failed"] > summary["ok"]:
        summary["flag"] = "review"
    if summary["ok"]:
        summary["mean"] = sum(r[2] for r in results) / summary["ok"]
    else:
        summary["mean"] = 0
    if ledger["balance"] < 0:
        summary["warning"] = "negative balance"
        if ledger["overdrafts"] > 3:
            summary["warning"] = "repeated overdrafts"
    summary["credits"] = ledger["credits"]
    summary["debits"] = ledger["debits"]
    summary["fees"] = ledger["fees"]
    summary["transfers"] = ledger["transfers"]
    summary["overdrafts"] = ledger["overdrafts"]
    summary["clean"] = ledger["clean_batches"]
    summary["partial"] = ledger["partial_batches"]
    return results, errors, summary


def empty_ledger():
    return {"credits": 0, "debits": 0, "balance": 0, "transfers": 0, "fees": 0, "overdrafts": 0,
            "failed_batches": 0, "partial_batches": 0, "clean_batches": 0}
