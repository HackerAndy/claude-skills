from app.repositories import order_repo
from app.schemas.order import OrderIn
from app.core.config import settings
from app.trace import traced, link


@traced
def list_orders():
    return order_repo.all()


@traced
def create_order(body: OrderIn):
    draft = f"draft:{body.sku}-{body.qty}"
    order = order_repo.insert(price(body.model_dump()))
    link(draft, f"order:{order['id']}", "saved")   # lineage: the request became order N
    return order


@traced
def price(d: dict) -> dict:
    return {**d, "total": round(d["qty"] * 9.99, 2)}


@traced
def get_order(order_id: int):
    order = order_repo.get(order_id)
    if order is None:
        raise LookupError(f"order {order_id} not found")
    return order
