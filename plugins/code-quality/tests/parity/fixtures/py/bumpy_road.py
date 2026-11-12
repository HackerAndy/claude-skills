"""Target smell: Bumpy Road (3 bumps, each nested 2 deep). Nesting and CC stay low."""


def normalise(record):
    if record.get("name"):
        if record["name"].isupper():
            record["name"] = record["name"].title()
    record["seen"] = True
    if record.get("email"):
        if " " in record["email"]:
            record["email"] = record["email"].strip()
    record["checked"] = True
    if record.get("phone"):
        if record["phone"].startswith("00"):
            record["phone"] = "+" + record["phone"][2:]
    return record
