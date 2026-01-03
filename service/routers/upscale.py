"""
Upscaling API router.
Provides Lanczos upscaling with alpha/transparency preservation.
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from config import get_settings, get_model_config
from services.upscaler import get_upscaler_service

logger = logging.getLogger(__name__)
router = APIRouter()


class UpscaleRequest(BaseModel):
    """Request model for upscaling via JSON."""
    image_base64: str
    scale: Optional[int] = 4
    preserve_alpha: Optional[bool] = True


@router.get("/info")
async def upscaler_info() -> dict:
    """
    Get information about the upscaler configuration.

    Returns available scale factors and settings.
    """
    model_config = get_model_config()
    upscaling_models = model_config.upscaling_models

    return {
        "method": "lanczos",
        "description": "High-quality Lanczos resampling with alpha preservation",
        "default_scale": 4,
        "max_scale": 8,
        "supported_formats": ["PNG", "JPEG", "WebP", "GIF"],
        "preserves_alpha": True,
        "cost": 0.0,
        "models": upscaling_models
    }


@router.post("/")
async def upscale_image(
    image: UploadFile = File(...),
    scale: int = Form(4),
    preserve_alpha: bool = Form(True)
) -> dict:
    """
    Upscale an image using Lanczos resampling.

    Args:
        image: Image file to upscale (PNG, JPEG, WebP)
        scale: Scale factor (1-8). Default: 4
        preserve_alpha: Whether to preserve transparency. Default: True

    Returns:
        Upscaled image with metadata.
    """
    settings = get_settings()

    # Validate scale
    if scale < 1 or scale > 8:
        raise HTTPException(
            status_code=400,
            detail="Scale must be between 1 and 8"
        )

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

    # Execute upscaling
    logger.info(
        f"Upscaling image: {image.filename}, "
        f"size: {len(content)} bytes, scale: {scale}x"
    )

    upscaler = get_upscaler_service()
    result = await upscaler.upscale(content, scale, preserve_alpha)

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Upscaling failed: {result.error}"
        )

    return result.to_dict()


@router.post("/base64")
async def upscale_base64(request: UpscaleRequest) -> dict:
    """
    Upscale an image from base64 input.

    Useful for chaining with background removal results.

    Args:
        request: JSON body with image_base64, scale, preserve_alpha

    Returns:
        Upscaled image with metadata.
    """
    # Validate scale
    scale = request.scale or 4
    if scale < 1 or scale > 8:
        raise HTTPException(
            status_code=400,
            detail="Scale must be between 1 and 8"
        )

    # Validate base64
    try:
        image_bytes = base64.b64decode(request.image_base64)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid base64 image: {e}"
        )

    # Check size
    settings = get_settings()
    if len(image_bytes) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Maximum size: {settings.max_upload_size / 1024 / 1024:.0f}MB"
        )

    # Execute upscaling
    upscaler = get_upscaler_service()
    result = await upscaler.upscale(
        image_bytes,
        scale,
        request.preserve_alpha if request.preserve_alpha is not None else True
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Upscaling failed: {result.error}"
        )

    return result.to_dict()


@router.post("/process")
async def process_pipeline(
    image: UploadFile = File(...),
    remove_background: bool = Form(True),
    upscale: bool = Form(True),
    scale: int = Form(4),
    bg_models: Optional[str] = Form(None)
) -> dict:
    """
    Combined pipeline: background removal + upscaling.

    Runs background removal shotgun, then upscales all successful results.
    This is a convenience endpoint for the full DTF workflow.

    Args:
        image: Image file to process
        remove_background: Whether to remove background. Default: True
        upscale: Whether to upscale after BG removal. Default: True
        scale: Upscale factor (1-8). Default: 4
        bg_models: Optional comma-separated list of BG removal models

    Returns:
        All processed results with both BG-removed and upscaled images.
    """
    settings = get_settings()

    # Validate inputs
    content = await image.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size / 1024 / 1024:.0f}MB"
        )

    if scale < 1 or scale > 8:
        raise HTTPException(
            status_code=400,
            detail="Scale must be between 1 and 8"
        )

    results = {
        "pipeline": [],
        "summary": {
            "background_removal": None,
            "upscaling": None
        }
    }

    # Step 1: Background removal
    if remove_background:
        from services.shotgun import get_shotgun_service

        model_list = None
        if bg_models:
            model_list = [m.strip() for m in bg_models.split(",")]

        shotgun = get_shotgun_service()
        bg_result = await shotgun.execute(content, model_list)
        results["summary"]["background_removal"] = {
            "successful": bg_result.successful_count,
            "failed": bg_result.failed_count,
            "total_time_ms": bg_result.total_time_ms
        }

        # Add each successful result
        for r in bg_result.successful_results:
            pipeline_item = {
                "model": r.model_name,
                "provider": r.provider,
                "bg_removal": r.to_dict()
            }

            # Step 2: Upscale each result
            if upscale and r.image_base64:
                upscaler = get_upscaler_service()
                up_result = await upscaler.upscale_base64(
                    r.image_base64,
                    scale,
                    preserve_alpha=True
                )
                pipeline_item["upscaled"] = up_result.to_dict()

            results["pipeline"].append(pipeline_item)

        if upscale:
            total_upscale_time = sum(
                item.get("upscaled", {}).get("processing_time_ms", 0)
                for item in results["pipeline"]
            )
            results["summary"]["upscaling"] = {
                "count": len(results["pipeline"]),
                "scale": scale,
                "total_time_ms": total_upscale_time
            }

    else:
        # Just upscale the original image
        if upscale:
            upscaler = get_upscaler_service()
            up_result = await upscaler.upscale(content, scale)
            results["pipeline"].append({
                "model": "original",
                "upscaled": up_result.to_dict()
            })
            results["summary"]["upscaling"] = {
                "count": 1,
                "scale": scale,
                "total_time_ms": up_result.processing_time_ms
            }

    return results
