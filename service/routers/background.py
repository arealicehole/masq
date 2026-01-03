"""
Background removal API router.
Provides shotgun endpoint for running multiple models in parallel.
"""

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from config import get_settings, get_model_config
from services.shotgun import get_shotgun_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ShotgunRequest(BaseModel):
    """Request model for shotgun background removal."""
    models: Optional[list[str]] = None


class ModelInfo(BaseModel):
    """Information about an available model."""
    name: str
    provider: str
    model_id: str
    cost_per_image: float
    enabled: bool
    notes: Optional[str] = None


@router.get("/models")
async def list_models() -> dict:
    """
    List all available background removal models.

    Returns information about each configured model including
    provider, cost, and current availability.
    """
    model_config = get_model_config()
    settings = get_settings()

    models = []
    for name, config in model_config.background_removal_models.items():
        provider = config.get("provider", "unknown")

        # Check if provider is available
        available = True
        if provider == "runware" and not settings.runware_api_key:
            available = False
        elif provider == "kie" and not settings.kie_api_key:
            available = False

        models.append({
            "id": name,
            "name": config.get("name", name),
            "provider": provider,
            "model_id": config.get("model_id", ""),
            "cost_per_image": config.get("cost_per_image", 0.0),
            "enabled": config.get("enabled", True),
            "available": available,
            "priority": config.get("priority", 99),
            "notes": config.get("notes", "")
        })

    # Sort by priority
    models.sort(key=lambda x: x["priority"])

    return {
        "models": models,
        "default_models": model_config.get_default_shotgun_models()
    }


@router.post("/")
async def remove_background(
    image: UploadFile = File(...),
    models: Optional[str] = Form(None)
) -> dict:
    """
    Remove background from an image using shotgun approach.

    Runs multiple models in parallel and returns all results,
    allowing the user to pick the best output.

    Args:
        image: Image file to process (PNG, JPEG, WebP)
        models: Optional comma-separated list of model IDs to use.
                If not provided, uses default models from config.

    Returns:
        Results from all models with images and metadata.
    """
    settings = get_settings()

    # Validate file size
    content = await image.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size / 1024 / 1024:.0f}MB"
        )

    # Validate content type
    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type: {content_type}. Expected image/*"
        )

    # Parse model list
    model_list = None
    if models:
        model_list = [m.strip() for m in models.split(",")]

    # Execute shotgun
    logger.info(f"Processing image: {image.filename}, size: {len(content)} bytes")
    shotgun = get_shotgun_service()
    result = await shotgun.execute(content, model_list)

    if result.successful_count == 0:
        raise HTTPException(
            status_code=500,
            detail="All models failed to process the image"
        )

    return result.to_dict()


@router.post("/single/{model_id}")
async def remove_background_single(
    model_id: str,
    image: UploadFile = File(...)
) -> dict:
    """
    Remove background using a single specific model.

    Useful for testing individual models or when you know
    which model works best for your use case.

    Args:
        model_id: ID of the model to use (e.g., "runware_rmbg2")
        image: Image file to process

    Returns:
        Result from the specified model.
    """
    settings = get_settings()
    model_config = get_model_config()

    # Validate model exists
    if model_id not in model_config.background_removal_models:
        raise HTTPException(
            status_code=404,
            detail=f"Model not found: {model_id}"
        )

    # Validate file
    content = await image.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size / 1024 / 1024:.0f}MB"
        )

    # Execute with single model
    shotgun = get_shotgun_service()
    result = await shotgun.execute(content, [model_id])

    if result.successful_count == 0:
        errors = [r.error for r in result.results if r.error]
        raise HTTPException(
            status_code=500,
            detail=f"Model failed: {errors[0] if errors else 'Unknown error'}"
        )

    # Return single result
    return result.results[0].to_dict()


@router.post("/log-selection")
async def log_selection(
    model_id: str = Form(...),
    job_id: Optional[str] = Form(None),
    notes: Optional[str] = Form(None)
) -> dict:
    """
    Log which model the user selected as the best result.

    This helps track model performance over time and can be
    used to improve model selection and recommendations.

    Args:
        model_id: ID of the model that produced the selected result
        job_id: Optional job/request ID for tracking
        notes: Optional notes about why this model was selected

    Returns:
        Confirmation of logged selection.
    """
    logger.info(
        f"User selected model: {model_id}, "
        f"job_id: {job_id}, notes: {notes}"
    )

    # TODO: In production, store this in a database for analytics

    return {
        "status": "logged",
        "model_id": model_id,
        "job_id": job_id
    }
