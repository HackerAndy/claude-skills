from fastapi import FastAPI
from app.routers import orders, customers
from app.trace.fastapi import TraceMiddleware

app = FastAPI(title="Orders API")
app.add_middleware(TraceMiddleware)
app.include_router(orders.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok"}
