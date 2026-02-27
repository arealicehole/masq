"""
HD Upscaler service using Real-ESRGAN.
Provides AI-based detail reconstruction.
"""

import asyncio
import base64
import io
import logging
import os
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Fix for torchvision 0.24+ compatibility with basicsr
try:
    import torchvision.transforms.functional as F
    class _FakeFunctionalTensor:
        rgb_to_grayscale = staticmethod(F.rgb_to_grayscale)
    import sys
    sys.modules['torchvision.transforms.functional_tensor'] = _FakeFunctionalTensor()
except Exception:
    pass

# Models directory - check multiple locations
ROOT_DIR = Path(__file__).parent.parent.parent
MODELS_DIRS = [
    ROOT_DIR / "models",
    ROOT_DIR / "cogs" / "masq" / "models",
    Path("/root/.u2net"),
]

# Singleton upscaler instances
_upscaler_cache: dict = {}

@dataclass
class HDUpscaleResult:
    """Result from HD upscaling operation."""
    success: bool
    image_base64: Optional[str] = None
    original_size: tuple[int, int] = (0, 0)
    upscaled_size: tuple[int, int] = (0, 0)
    scale_factor: int = 4
    has_alpha: bool = False
    processing_time_ms: float = 0
    error: Optional[str] = None
    model_used: str = ""

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
            "has_alpha": self.has_alpha,
            "model_used": self.model_used,
            "method": "real-esrgan"
        }

        if self.success and self.image_base64:
            result["image_base64"] = self.image_base64

        if self.error:
            result["error"] = self.error

        return result


def _find_model(model_name: str) -> Optional[Path]:
    """Find model file in known locations."""
    for models_dir in MODELS_DIRS:
        model_path = models_dir / f"{model_name}.pth"
        if model_path.exists():
            return model_path
    return None


class RealESRGANUpscaler:
    """Real-ESRGAN upscaler with alpha preservation."""

    def __init__(
        self,
        model_name: str = "RealESRGAN_x4plus",
        tile: int = 256,
        gpu_id: Optional[int] = None,
        use_half: bool = False
    ):
        self.model_name = model_name
        self.tile = tile
        self.gpu_id = gpu_id
        self.use_half = use_half if gpu_id is not None else False
        self._upsampler = None

    def _get_upsampler(self):
        """Lazy-load the upsampler."""
        if self._upsampler is not None:
            return self._upsampler

        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet

        model_path = _find_model(self.model_name)
        if not model_path:
            raise FileNotFoundError(f"Model {self.model_name}.pth not found.")

        if self.model_name == "RealESRGAN_x4plus":
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        elif self.model_name == "RealESRGAN_x4plus_anime_6B":
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
        else:
            raise ValueError(f"Unknown model: {self.model_name}")

        self._upsampler = RealESRGANer(
            scale=4,
            model_path=str(model_path),
            model=model,
            tile=self.tile,
            tile_pad=10,
            pre_pad=0,
            half=self.use_half,
            gpu_id=self.gpu_id
        )
        return self._upsampler

    async def upscale(self, image: Image.Image, scale: int = 4) -> Image.Image:
        import cv2
        upsampler = self._get_upsampler()

        if image.mode == "RGBA":
            img_array = np.array(image)
            img_input = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGRA)
        else:
            img_array = np.array(image.convert("RGB"))
            img_input = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        def _do_enhance():
            return upsampler.enhance(img_input, outscale=scale)

        output, _ = await asyncio.to_thread(_do_enhance)

        if output.shape[2] == 4:
            output_rgba = cv2.cvtColor(output, cv2.COLOR_BGRA2RGBA)
            result = Image.fromarray(output_rgba, mode="RGBA")
        else:
            output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
            result = Image.fromarray(output_rgb, mode="RGB")

        return result


class HDUpscalerService:
    """Service for HD upscaling using Real-ESRGAN."""

    def __init__(self, tile: int = 256):
        self.tile = tile
        self.use_gpu = os.getenv("USE_GPU", "false").lower() == "true"

    async def upscale(
        self,
        image_bytes: bytes,
        scale: int = 4,
        model: str = "default"
    ) -> HDUpscaleResult:
        start = time.perf_counter()
        try:
            img = Image.open(io.BytesIO(image_bytes))
            original_size = img.size
            has_alpha = img.mode == "RGBA"

            model_name = "RealESRGAN_x4plus_anime_6B" if model == "anime" else "RealESRGAN_x4plus"
            
            cache_key = f"{model_name}_{self.tile}_{self.use_gpu}"
            if cache_key not in _upscaler_cache:
                _upscaler_cache[cache_key] = RealESRGANUpscaler(
                    model_name=model_name,
                    tile=self.tile,
                    gpu_id=0 if self.use_gpu else None,
                    use_half=self.use_gpu
                )
            upscaler = _upscaler_cache[cache_key]

            result_img = await upscaler.upscale(img, scale)

            output_buffer = io.BytesIO()
            # Save as PNG for maximum quality on service
            result_img.save(output_buffer, format="PNG", optimize=True)
            result_bytes = output_buffer.getvalue()
            result_base64 = base64.b64encode(result_bytes).decode("utf-8")

            elapsed = (time.perf_counter() - start) * 1000

            return HDUpscaleResult(
                success=True,
                image_base64=result_base64,
                original_size=original_size,
                upscaled_size=result_img.size,
                scale_factor=scale,
                has_alpha=has_alpha and result_img.mode == "RGBA",
                processing_time_ms=elapsed,
                model_used=model_name
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception(f"HD Upscaling error: {e}")
            return HDUpscaleResult(success=False, error=str(e), processing_time_ms=elapsed)

    async def upscale_base64(self, image_base64: str, scale: int = 4, model: str = "default") -> HDUpscaleResult:
        try:
            image_bytes = base64.b64decode(image_base64)
            return await self.upscale(image_bytes, scale, model)
        except Exception as e:
            return HDUpscaleResult(success=False, error=f"Invalid base64: {e}")

_hd_upscaler_service = None

def get_hd_upscaler_service() -> HDUpscalerService:
    global _hd_upscaler_service
    if _hd_upscaler_service is None:
        _hd_upscaler_service = HDUpscalerService()
    return _hd_upscaler_service
