from pydantic import BaseModel
class OrderIn(BaseModel):
    sku: str
    qty: int
class OrderOut(OrderIn):
    id: int
