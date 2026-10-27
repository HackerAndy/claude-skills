from app.models.order import Order
from app.core.config import settings
from app.trace import traced, data

_DB = {}


@traced
def all():
    data(*(f"order:{i}" for i in _DB), role="out")
    return list(_DB.values())


@traced
def get(order_id):
    return _DB.get(order_id)


@traced
def insert(d):
    i = len(_DB) + 1
    _DB[i] = {"id": i, **d}
    data(f"order:{i}", role="out")
    return _DB[i]
