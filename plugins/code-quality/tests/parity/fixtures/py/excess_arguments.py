"""Target smell: Excess Number of Function Arguments (6). Body is trivial."""


def create_user(name, email, role, team, timezone, locale):
    return {"name": name, "email": email, "role": role, "team": team, "tz": timezone, "locale": locale}
