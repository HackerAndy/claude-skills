from app.repositories import customer_repo

def get(customer_id: int):
    return customer_repo.get(customer_id)
