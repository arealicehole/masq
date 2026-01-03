"""
Image Processing Service - FastAPI Entry Point
5-Model Shotgun Background Removal + Lanczos Upscaling
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings, get_model_config

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger.info("Starting Image Processing Service...")

    # Create temp directory
    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Temp directory: {temp_dir}")

    # Load model configuration
    try:
        model_config = get_model_config()
        enabled_models = model_config.get_enabled_bg_models()
        logger.info(f"Loaded {len(enabled_models)} background removal models")
        for name, config in enabled_models.items():
            logger.info(f"  - {name}: {config.get('name')} ({config.get('provider')})")
    except FileNotFoundError as e:
        logger.error(f"Failed to load model config: {e}")

    # Validate API keys
    if not settings.runware_api_key:
        logger.warning("RUNWARE_API_KEY not set - Runware models will be unavailable")
    if not settings.kie_api_key:
        logger.warning("KIE_API_KEY not set - Kie.ai models will be unavailable")

    yield

    # Shutdown
    logger.info("Shutting down Image Processing Service...")


app = FastAPI(
    title="Image Processing Service",
    description="5-Model Shotgun Background Removal + Lanczos Upscaling API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "detail": str(exc) if settings.log_level == "DEBUG" else None
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    model_config = get_model_config()
    enabled_models = model_config.get_enabled_bg_models()

    return {
        "status": "healthy",
        "service": "img-proc",
        "version": "1.0.0",
        "models": {
            "background_removal": list(enabled_models.keys()),
            "upscaling": list(model_config.upscaling_models.keys())
        },
        "providers": {
            "runware": bool(settings.runware_api_key),
            "kie": bool(settings.kie_api_key),
            "local": True
        }
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "Image Processing Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "remove_background": "/remove-background",
            "upscale": "/upscale",
            "process": "/process"
        },
        "docs": "/docs"
    }


# Import and include routers
from routers import background, upscale

app.include_router(background.router, prefix="/remove-background", tags=["Background Removal"])
app.include_router(upscale.router, prefix="/upscale", tags=["Upscaling"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )
