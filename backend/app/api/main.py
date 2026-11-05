"""OptiPack FastAPI Application Orchestrator.

Main entrypoint for the OptiPack backend server.
Runs on port 8000 by default and serves REST endpoints under /api/v1.
"""

import os
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

# Enable CORS for local frontend development (Vite default :5173) and production deployments (Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static assets directory for serving cropped item preview images
STATIC_ASSETS_DIR = Path(__file__).resolve().parent / "static" / "crops"
STATIC_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/v1/assets/crops", StaticFiles(directory=str(STATIC_ASSETS_DIR)), name="crops")
app.mount("/api/v1/assets", StaticFiles(directory=str(STATIC_ASSETS_DIR)), name="assets")

# Include API routers under /api/v1 prefix
app.include_router(orders.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")


@app.get("/", tags=["System"])
async def root():
    """Root endpoint confirming API status and documentation links."""
    return {
        "status": "ok",
        "app": "OptiPack API",
        "version": "1.0.0",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/api/v1", tags=["System"])
async def api_v1_status():
    """API v1 base discovery endpoint."""
    return {
        "status": "ok",
        "app": "OptiPack API v1",
        "docs": "/docs",
        "endpoints": {
            "orders": "/api/v1/orders",
            "catalog": "/api/v1/catalog",
        },
    }


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint confirming API status and AI configuration."""
    has_meta = bool(os.getenv("MODEL_API_KEY", "").strip())
    has_baseten = bool((
        os.getenv("BASETEN_API_KEY")
        or os.getenv("BaseTen_API")
        or os.getenv("BASETEN_API", "")
    ).strip())
    return {
        "status": "ok",
        "app": "OptiPack",
        "contract_version": "1.0.0",
        "meta_api_configured": has_meta,
        "baseten_api_configured": has_baseten,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.api.main:app", host="0.0.0.0", port=8000, reload=True)
