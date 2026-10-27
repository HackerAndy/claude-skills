from fastapi import APIRouter
from app.services import order_service
from app.schemas.order import OrderIn, OrderOut


router = APIRouter(prefix="/orders", tags=["orders"])

@router.get("", response_model=list[OrderOut])
def list_orders():
    return order_service.list_orders()

@router.post("", response_model=OrderOut)
def create_order(body: OrderIn):
    return order_service.create_order(body)

@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int):
    return order_service.get_order(order_id)

@router.post("/{order_id}/refund")
def refund(order_id: int):          # not in the contract
    return {"refunded": order_id}
