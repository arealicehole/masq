"""
Real-ESRGAN HD upscaler with alpha preservation.

Provides AI-based upscaling that can reconstruct detail from low-quality sources.
Slower than classical Lanczos but much better quality for degraded images.
"""

import numpy as np
from pathlib import Path
from PIL import Image
from typing import Optional
from dataclasses import dataclass
import sys

# Fix for torchvision 0.24+ compatibility with basicsr
# Must be done before importing realesrgan/basicsr
try:
    import torchvision.transforms.functional as F
    class _FakeFunctionalTensor:
        rgb_to_grayscale = staticmethod(F.rgb_to_grayscale)
    sys.modules['torchvision.transforms.functional_tensor'] = _FakeFunctionalTensor()
except Exception:
    pass

# Models directory - check multiple locations
MODELS_DIRS = [
    Path(__file__).parent / "models",
    Path(__file__).parent.parent.parent / "models",
    Path(__file__).parent.parent.parent / "test" / "models",
]


@dataclass
class HDUpscaleResult:
    """Result from HD upscaling."""
    success: bool
    image_bytes: Optional[bytes] = None
    original_size: tuple = (0, 0)
    upscaled_size: tuple = (0, 0)
    scale_factor: int = 4
    has_alpha: bool = False
    processing_time_ms: float = 0
    error: Optional[str] = None
    model_used: str = ""


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
        """
        Initialize upscaler.

        Args:
            model_name: Model to use (RealESRGAN_x4plus or RealESRGAN_x4plus_anime_6B)
            tile: Tile size for processing (lower = less VRAM, slower)
            gpu_id: GPU ID or None for CPU
            use_half: Use half precision (faster on GPU, not supported on CPU)
        """
        self.model_name = model_name
        self.tile = tile
        self.gpu_id = gpu_id
        self.use_half = use_half if gpu_id is not None else False
        self._upsampler = None

    def _get_upsampler(self):
        """Lazy-load the upsampler."""
        if self._upsampler is not None:
            return self._upsampler

        try:
            from realesrgan import RealESRGANer
            from basicsr.archs.rrdbnet_arch import RRDBNet
        except ImportError:
            raise ImportError(
                "Real-ESRGAN not installed. Run: pip install realesrgan basicsr"
            )

        model_path = _find_model(self.model_name)
        if not model_path:
            raise FileNotFoundError(
                f"Model {self.model_name}.pth not found. "
                f"Searched: {[str(d) for d in MODELS_DIRS]}"
            )

        # Model configuration
        if self.model_name == "RealESRGAN_x4plus":
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64,
                num_block=23, num_grow_ch=32, scale=4
            )
        elif self.model_name == "RealESRGAN_x4plus_anime_6B":
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64,
                num_block=6, num_grow_ch=32, scale=4
            )
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
        """
        Upscale image using Real-ESRGAN.

        Args:
            image: PIL Image (RGB or RGBA)
            scale: Scale factor (currently only 4x supported by model)

        Returns:
            Upscaled PIL Image with alpha preserved if input had alpha
        """
        import asyncio
        import cv2

        upsampler = self._get_upsampler()

        # Convert PIL to numpy (BGR for OpenCV)
        if image.mode == "RGBA":
            img_array = np.array(image)
            img_bgra = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGRA)
            img_input = img_bgra
        else:
            img_array = np.array(image.convert("RGB"))
            img_input = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Run heavy CPU work in thread pool to avoid blocking event loop
        def _do_enhance():
            return upsampler.enhance(img_input, outscale=scale)

        output, _ = await asyncio.to_thread(_do_enhance)

        # Convert back to PIL
        if output.shape[2] == 4:
            output_rgba = cv2.cvtColor(output, cv2.COLOR_BGRA2RGBA)
            result = Image.fromarray(output_rgba, mode="RGBA")
        else:
            output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
            result = Image.fromarray(output_rgb, mode="RGB")

        return result


async def upscale_hd(
    image_bytes: bytes,
    scale: int = 4,
    model: str = "default",
    tile: int = 256
) -> HDUpscaleResult:
    """
    HD upscale using Real-ESRGAN.

    Args:
        image_bytes: Input image as bytes
        scale: Scale factor (4x recommended)
        model: "default" for general, "anime" for illustrations
        tile: Tile size (lower for less memory)

    Returns:
        HDUpscaleResult with upscaled image bytes
    """
    import io
    import time

    start = time.perf_counter()

    try:
        # Load image
        img = Image.open(io.BytesIO(image_bytes))
        original_size = img.size
        has_alpha = img.mode == "RGBA"

        # Select model
        model_name = (
            "RealESRGAN_x4plus_anime_6B" if model == "anime"
            else "RealESRGAN_x4plus"
        )

        # Create upscaler
        upscaler = RealESRGANUpscaler(
            model_name=model_name,
            tile=tile,
            gpu_id=None,  # CPU for now
            use_half=False
        )

        # Upscale
        result_img = await upscaler.upscale(img, scale)

        # Convert to bytes (WebP for smaller file size with alpha support)
        output_buffer = io.BytesIO()
        result_img.save(output_buffer, format="WEBP", quality=95, lossless=False)
        result_bytes = output_buffer.getvalue()

        elapsed = (time.perf_counter() - start) * 1000

        return HDUpscaleResult(
            success=True,
            image_bytes=result_bytes,
            original_size=original_size,
            upscaled_size=result_img.size,
            scale_factor=scale,
            has_alpha=has_alpha and result_img.mode == "RGBA",
            processing_time_ms=elapsed,
            model_used=model_name
        )

    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return HDUpscaleResult(
            success=False,
            error=str(e),
            processing_time_ms=elapsed
        )
