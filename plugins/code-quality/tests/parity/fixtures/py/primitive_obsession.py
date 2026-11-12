"""Target smell: Primitive Obsession and String Heavy Function Arguments.

Fifteen functions whose arguments are all bare str / int / float / bool. CodeScene needs
about this many before the file-level percentage rule fires; five functions were not enough.
"""


def price_with_tax(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 1}-{strict}"


def discount(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 2}-{strict}"


def convert(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 3}-{strict}"


def round_to(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 4}-{strict}"


def clamp(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 5}-{strict}"


def format_money(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 6}-{strict}"


def percent(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 7}-{strict}"


def margin(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 8}-{strict}"


def markup(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 9}-{strict}"


def split_cost(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 10}-{strict}"


def weight_band(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 11}-{strict}"


def zone_for(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 12}-{strict}"


def eta_days(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 13}-{strict}"


def slug(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 14}-{strict}"


def initials(code: str, region: str, amount: float, strict: bool) -> str:
    return f"{code}-{region}-{amount * 15}-{strict}"
