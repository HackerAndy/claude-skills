from fastapi import APIRouter
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])

@router.get("/{customer_id}")
def get_customer(customer_id: int):
    return customer_service.get(customer_id)
