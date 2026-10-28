"""OptiPack FastAPI Application Orchestrator.

Main entrypoint for the OptiPack backend server.
Runs on port 8000 by default and serves REST endpoints under /api/v1.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.app.api.routers import catalog, orders


app = FastAPI(
    title="OptiPack API",
    version="1.0.0",
    description="E-Commerce Multi-Item 3D Cartonization & Packing Assistant API",
)

# Enable CORS for local frontend development (Vite default :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static assets directory for serving cropped item preview images
STATIC_ASSETS_DIR = Path(__file__).resolve().parent / "static" / "crops"
STATIC_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/v1/assets/crops", StaticFiles(directory=str(STATIC_ASSETS_DIR)), name="crops")

# Include API routers under /api/v1 prefix
app.include_router(orders.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint confirming API status."""
    return {"status": "ok", "app": "OptiPack", "contract_version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.api.main:app", host="0.0.0.0", port=8000, reload=True)
