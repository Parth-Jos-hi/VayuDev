from fastapi import FastAPI
from app.core.config import settings
app = FastAPI(
    title=settings.name,
    description="VayuDev Air Quality Monitoring and Recommendation API",
    version=settings.version
)

@app.get("/api/v1/health")
def root():
    return {
        "status": "ok",
        "message": "VayuDev API is running"
    }