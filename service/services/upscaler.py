"""
Upscaler service using Lanczos resampling.
Preserves alpha/transparency - critical for DTF printing.
"""

import asyncio
import base64
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound operations
_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class UpscaleResult:
    """Result from upscaling operation."""
    success: bool
    image_base64: Optional[str] = None
    original_size: tuple[int, int] = (0, 0)
    upscaled_size: tuple[int, int] = (0, 0)
    scale_factor: float = 1.0
    processing_time_ms: float = 0.0
    error: Optional[str] = None
    has_alpha: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        result = {
            "success": self.success,
            "original_size": {
                "width": self.original_size[0],
                "height": self.original_size[1]
            },
            "upscaled_size": {
                "width": self.upscaled_size[0],
                "height": self.upscaled_size[1]
            },
            "scale_factor": self.scale_factor,
            "processing_time_ms": self.processing_time_ms,
            "has_alpha": self.has_alpha
        }

        if self.success and self.image_base64:
            result["image_base64"] = self.image_base64

        if self.error:
            result["error"] = self.error

        return result


class UpscalerService:
    """
    Service for upscaling images using Lanczos resampling.

    Key features:
    - Preserves alpha channel (transparency)
    - No size limits (unlike API-based upscalers)
    - High-quality Lanczos algorithm
    - Zero cost (runs locally)
    """

    def __init__(self, default_scale: int = 4, max_scale: int = 8):
        self.default_scale = default_scale
        self.max_scale = max_scale

    def _upscale_sync(
        self,
        image_bytes: bytes,
        scale: int,
        preserve_alpha: bool = True
    ) -> tuple[bytes, tuple[int, int], tuple[int, int], bool]:
        """
        Synchronous upscaling for thread pool execution.

        Returns:
            Tuple of (result_bytes, original_size, upscaled_size, has_alpha)
        """
        # Load image
        input_image = Image.open(io.BytesIO(image_bytes))
        original_size = input_image.size
        has_alpha = input_image.mode == "RGBA"

        # Calculate new size
        new_width = original_size[0] * scale
        new_height = original_size[1] * scale
        new_size = (new_width, new_height)

        # Ensure we preserve alpha if present
        if preserve_alpha and has_alpha:
            # Keep RGBA mode
            output_image = input_image.resize(new_size, Image.Resampling.LANCZOS)
        else:
            # Convert to RGB if no alpha or not preserving
            if input_image.mode == "RGBA":
                # Convert RGBA to RGB with white background
                rgb_image = Image.new("RGB", input_image.size, (255, 255, 255))
                rgb_image.paste(input_image, mask=input_image.split()[3])
                output_image = rgb_image.resize(new_size, Image.Resampling.LANCZOS)
                has_alpha = False
            else:
                if input_image.mode != "RGB":
                    input_image = input_image.convert("RGB")
                output_image = input_image.resize(new_size, Image.Resampling.LANCZOS)

        # Save to bytes
        output_buffer = io.BytesIO()
        if has_alpha:
            output_image.save(output_buffer, format="PNG", optimize=True)
        else:
            output_image.save(output_buffer, format="PNG", optimize=True)

        return output_buffer.getvalue(), original_size, new_size, has_alpha

    async def upscale(
        self,
        image_bytes: bytes,
        scale: Optional[int] = None,
        preserve_alpha: bool = True,
        timeout: float = 60.0
    ) -> UpscaleResult:
        """
        Upscale an image using Lanczos resampling.

        Args:
            image_bytes: Raw image bytes (PNG, JPEG, etc.)
            scale: Scale factor (1-max_scale). Defaults to default_scale.
            preserve_alpha: Whether to preserve transparency. Default True.
            timeout: Timeout in seconds.

        Returns:
            UpscaleResult with the upscaled image
        """
        start_time = time.time()

        # Validate and set scale
        if scale is None:
            scale = self.default_scale
        scale = max(1, min(scale, self.max_scale))

        try:
            # Run upscaling in thread pool
            loop = asyncio.get_event_loop()
            result_bytes, original_size, upscaled_size, has_alpha = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    self._upscale_sync,
                    image_bytes,
                    scale,
                    preserve_alpha
                ),
                timeout=timeout
            )

            result_base64 = base64.b64encode(result_bytes).decode("utf-8")
            processing_time = (time.time() - start_time) * 1000

            return UpscaleResult(
                success=True,
                image_base64=result_base64,
                original_size=original_size,
                upscaled_size=upscaled_size,
                scale_factor=scale,
                processing_time_ms=processing_time,
                has_alpha=has_alpha
            )

        except asyncio.TimeoutError:
            return UpscaleResult(
                success=False,
                error=f"Upscaling timeout after {timeout}s"
            )
        except Exception as e:
            logger.exception(f"Upscaling error: {e}")
            return UpscaleResult(
                success=False,
                error=str(e)
            )

    async def upscale_base64(
        self,
        image_base64: str,
        scale: Optional[int] = None,
        preserve_alpha: bool = True,
        timeout: float = 60.0
    ) -> UpscaleResult:
        """
        Upscale an image from base64 string.

        Args:
            image_base64: Base64-encoded image
            scale: Scale factor
            preserve_alpha: Whether to preserve transparency
            timeout: Timeout in seconds

        Returns:
            UpscaleResult with the upscaled image
        """
        try:
            image_bytes = base64.b64decode(image_base64)
            return await self.upscale(image_bytes, scale, preserve_alpha, timeout)
        except Exception as e:
            return UpscaleResult(
                success=False,
                error=f"Invalid base64 image: {e}"
            )


# Singleton instance
_upscaler_service: Optional[UpscalerService] = None


def get_upscaler_service() -> UpscalerService:
    """Get the singleton upscaler service instance."""
    global _upscaler_service
    if _upscaler_service is None:
        _upscaler_service = UpscalerService()
    return _upscaler_service
