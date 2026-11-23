from fastapi import FastAPI
from app.core.config import settings
from app.api.auth import router as auth_router
app = FastAPI(
    title=settings.name,
    description="VayuDev Air Quality Monitoring and Recommendation API",
    version=settings.version
)
app.include_router(auth_router,
            prefix = "/api/v1")

@app.get("/api/v1/health")
def root():
    return {
        "status": "ok",
        "message": "VayuDev API is running"
    }