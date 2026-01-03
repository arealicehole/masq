"""
Masq Core Engine
Background removal & upscaling engine.

Requires: Pillow, rembg (for local models), httpx (for API calls)
API keys optional - local models work without them.
"""

import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound local model execution
_executor = ThreadPoolExecutor(max_workers=2)


class ModelStatus(str, Enum):
    """Status of a model execution."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass
class ModelResult:
    """Result from a single background removal model."""
    model_id: str
    model_name: str
    provider: str  # runware, kie, local
    status: ModelStatus
    image_bytes: Optional[bytes] = None
    image_base64: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    cost: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == ModelStatus.SUCCESS and self.image_bytes is not None

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "provider": self.provider,
            "status": self.status.value,
            "processing_time_ms": self.processing_time_ms,
            "cost": self.cost,
            "error": self.error,
            "has_image": self.image_bytes is not None
        }


@dataclass
class ShotgunResult:
    """Result from shotgun (multi-model) background removal."""
    results: list[ModelResult] = field(default_factory=list)
    total_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def successful(self) -> list[ModelResult]:
        return [r for r in self.results if r.is_success]

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self.results)

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "successful_count": len(self.successful),
            "failed_count": len(self.results) - len(self.successful),
            "total_time_ms": self.total_time_ms,
            "total_cost": self.total_cost
        }


@dataclass
class UpscaleResult:
    """Result from Lanczos upscaling."""
    success: bool
    image_bytes: Optional[bytes] = None
    image_base64: Optional[str] = None
    original_size: tuple[int, int] = (0, 0)
    upscaled_size: tuple[int, int] = (0, 0)
    scale_factor: int = 1
    processing_time_ms: float = 0.0
    has_alpha: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "original_size": {"width": self.original_size[0], "height": self.original_size[1]},
            "upscaled_size": {"width": self.upscaled_size[0], "height": self.upscaled_size[1]},
            "scale_factor": self.scale_factor,
            "processing_time_ms": self.processing_time_ms,
            "has_alpha": self.has_alpha,
            "error": self.error
        }


# Model configurations
MODELS = {
    # Runware API models
    "runware_rmbg2": {
        "name": "RMBG 2.0",
        "provider": "runware",
        "model_id": "runware:110@1",
        "cost": 0.0006,
        "priority": 1,
        "notes": "Best overall performer"
    },
    "runware_birefnet_portrait": {
        "name": "BiRefNet Portrait",
        "provider": "runware",
        "model_id": "runware:112@10",
        "cost": 0.0006,
        "priority": 2,
        "notes": "Good for portraits/people"
    },
    # Kie.ai API model
    "kie_recraft": {
        "name": "Recraft BG",
        "provider": "kie",
        "model_id": "recraft/remove-background",
        "cost": 0.005,
        "priority": 3
    },
    # Local models (FREE)
    "local_birefnet": {
        "name": "BiRefNet General",
        "provider": "local",
        "model_id": "birefnet-general",
        "cost": 0.0,
        "priority": 4
    },
    "local_isnet": {
        "name": "ISNet",
        "provider": "local",
        "model_id": "isnet-general-use",
        "cost": 0.0,
        "priority": 5
    }
}

DEFAULT_SHOTGUN_MODELS = [
    "runware_rmbg2",
    "runware_birefnet_portrait",
    "kie_recraft",
    "local_birefnet",
    "local_isnet"
]


class Masq:
    """
    Masq Image Processing Engine.

    Background removal via shotgun (5 models in parallel) or single model.
    Upscaling via Lanczos (preserves alpha/transparency).
    """

    def __init__(
        self,
        runware_key: Optional[str] = None,
        kie_key: Optional[str] = None,
        timeout: int = 120
    ):
        self.runware_key = runware_key
        self.kie_key = kie_key
        self.timeout = timeout
        self._runware_client = None
        self._local_sessions = {}

    # ==================== Background Removal ====================

    async def remove_background(
        self,
        image_bytes: bytes,
        models: Optional[list[str]] = None
    ) -> ShotgunResult:
        """
        Remove background using shotgun approach (multiple models in parallel).

        Args:
            image_bytes: Raw image bytes
            models: List of model IDs to use. Defaults to all 5 models.

        Returns:
            ShotgunResult with all model results
        """
        start = time.time()
        result = ShotgunResult()

        if models is None:
            models = DEFAULT_SHOTGUN_MODELS

        # Filter to available models
        available = self._get_available_models(models)
        if not available:
            logger.warning("No models available for background removal")
            return result

        logger.info(f"Shotgun firing {len(available)} models: {available}")

        # Run all models in parallel with individual timeouts
        tasks = [
            asyncio.create_task(self._run_model(model_id, image_bytes))
            for model_id in available
        ]

        # Wait for all tasks with timeout, but collect partial results
        done, pending = await asyncio.wait(
            tasks,
            timeout=self.timeout + 30,
            return_when=asyncio.ALL_COMPLETED
        )

        # Cancel any pending tasks
        for task in pending:
            task.cancel()
            logger.warning(f"Model task timed out and was cancelled")

        # Collect results from completed tasks
        for task in done:
            try:
                r = task.result()
                if isinstance(r, ModelResult):
                    result.results.append(r)
            except Exception as e:
                logger.error(f"Model task exception: {e}")

        result.total_time_ms = (time.time() - start) * 1000
        logger.info(
            f"Shotgun complete: {len(result.successful)}/{len(result.results)} successful, "
            f"{result.total_time_ms:.0f}ms"
        )

        return result

    async def remove_background_single(
        self,
        image_bytes: bytes,
        model_id: str
    ) -> ModelResult:
        """
        Remove background using a single specified model.

        Args:
            image_bytes: Raw image bytes
            model_id: Model ID to use (e.g., "runware_rmbg2")

        Returns:
            ModelResult from the specified model
        """
        if model_id not in MODELS:
            return ModelResult(
                model_id=model_id,
                model_name="Unknown",
                provider="unknown",
                status=ModelStatus.FAILED,
                error=f"Unknown model: {model_id}"
            )

        return await self._run_model(model_id, image_bytes)

    def _get_available_models(self, requested: list[str]) -> list[str]:
        """Filter to models that are available based on API keys."""
        available = []
        for model_id in requested:
            if model_id not in MODELS:
                continue

            config = MODELS[model_id]
            provider = config["provider"]

            if provider == "runware" and not self.runware_key:
                continue
            if provider == "kie" and not self.kie_key:
                continue
            # Local models always available

            available.append(model_id)

        return available

    async def _run_model(self, model_id: str, image_bytes: bytes) -> ModelResult:
        """Run a single background removal model."""
        config = MODELS[model_id]
        provider = config["provider"]
        start = time.time()

        try:
            if provider == "runware":
                result_bytes = await self._run_runware(config, image_bytes)
            elif provider == "kie":
                result_bytes = await self._run_kie(config, image_bytes)
            elif provider == "local":
                result_bytes = await self._run_local(config, image_bytes)
            else:
                raise ValueError(f"Unknown provider: {provider}")

            return ModelResult(
                model_id=model_id,
                model_name=config["name"],
                provider=provider,
                status=ModelStatus.SUCCESS,
                image_bytes=result_bytes,
                image_base64=base64.b64encode(result_bytes).decode(),
                processing_time_ms=(time.time() - start) * 1000,
                cost=config["cost"]
            )

        except asyncio.TimeoutError:
            return ModelResult(
                model_id=model_id,
                model_name=config["name"],
                provider=provider,
                status=ModelStatus.TIMEOUT,
                error=f"Timeout after {self.timeout}s",
                processing_time_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            logger.exception(f"Model {model_id} failed: {e}")
            return ModelResult(
                model_id=model_id,
                model_name=config["name"],
                provider=provider,
                status=ModelStatus.FAILED,
                error=str(e),
                processing_time_ms=(time.time() - start) * 1000
            )

    async def _run_runware(self, config: dict, image_bytes: bytes) -> bytes:
        """Execute Runware API background removal."""
        from runware import Runware, IImageBackgroundRemoval

        if self._runware_client is None:
            self._runware_client = Runware(api_key=self.runware_key)
            await self._runware_client.connect()

        # Convert to data URI
        b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:image/png;base64,{b64}"

        request = IImageBackgroundRemoval(
            inputImage=data_uri,
            model=config["model_id"],
            outputFormat="PNG"
        )

        results = await asyncio.wait_for(
            self._runware_client.imageBackgroundRemoval(request),
            timeout=self.timeout
        )

        if not results:
            raise ValueError("No results from Runware")

        # Fetch result image
        import httpx
        result = results[0]
        if hasattr(result, "imageURL") and result.imageURL:
            async with httpx.AsyncClient() as client:
                resp = await client.get(result.imageURL)
                resp.raise_for_status()
                return resp.content
        elif hasattr(result, "imageBase64") and result.imageBase64:
            return base64.b64decode(result.imageBase64)
        else:
            raise ValueError("No image in Runware response")

    async def _run_kie(self, config: dict, image_bytes: bytes) -> bytes:
        """Execute Kie.ai API background removal."""
        import httpx

        base_url = "https://api.kie.ai/api/v1"
        upload_url = "https://kieai.redpandaai.co/api/file-stream-upload"

        async with httpx.AsyncClient() as client:
            # Upload to CDN (requires auth + uploadPath)
            resp = await client.post(
                upload_url,
                headers={"Authorization": f"Bearer {self.kie_key}"},
                files={"file": ("image.png", image_bytes, "image/png")},
                data={"uploadPath": "masq-uploads"},
                timeout=30
            )
            resp.raise_for_status()
            cdn_data = resp.json()
            if not cdn_data.get("success"):
                raise ValueError(f"CDN upload failed: {cdn_data}")
            image_url = cdn_data.get("data", {}).get("downloadUrl") or cdn_data.get("data", {}).get("fileUrl") or cdn_data.get("data", {}).get("url")
            if not image_url:
                raise ValueError(f"No URL in CDN upload response: {cdn_data}")

            # Submit task using updated endpoint
            resp = await client.post(
                f"{base_url}/jobs/createTask",
                headers={
                    "Authorization": f"Bearer {self.kie_key}",
                    "Content-Type": "application/json"
                },
                json={"model": config["model_id"], "input": {"image": image_url}},
                timeout=30
            )
            resp.raise_for_status()
            task_data = resp.json()
            if not task_data or task_data.get("code") != 200:
                raise ValueError(f"Kie API error: {task_data}")
            task_id = task_data.get("data", {}).get("taskId")
            if not task_id:
                raise ValueError(f"No taskId in Kie response: {task_data}")

            # Poll for completion using recordInfo endpoint
            for _ in range(60):
                resp = await client.get(
                    f"{base_url}/jobs/recordInfo",
                    headers={"Authorization": f"Bearer {self.kie_key}"},
                    params={"taskId": task_id},
                    timeout=10
                )
                resp.raise_for_status()
                poll_data = resp.json()
                status_data = poll_data.get("data", {})
                state = status_data.get("state", "").lower()

                if state == "success":
                    # resultJson is a JSON string containing resultUrls
                    result_json_str = status_data.get("resultJson", "{}")
                    import json
                    result_json = json.loads(result_json_str)
                    result_urls = result_json.get("resultUrls", [])
                    if not result_urls:
                        raise ValueError(f"No resultUrls in Kie response: {status_data}")
                    resp = await client.get(result_urls[0], timeout=30)
                    resp.raise_for_status()
                    return resp.content

                if state == "fail":
                    raise ValueError(f"Kie task failed: {status_data.get('failMsg')}")

                await asyncio.sleep(2)

            raise TimeoutError("Kie task did not complete")

    async def _run_local(self, config: dict, image_bytes: bytes) -> bytes:
        """Execute local rembg model."""
        model_id = config["model_id"]

        def _process():
            from rembg import remove, new_session

            if model_id not in self._local_sessions:
                self._local_sessions[model_id] = new_session(model_id)

            session = self._local_sessions[model_id]
            img = Image.open(io.BytesIO(image_bytes))
            result = remove(img, session=session)

            buf = io.BytesIO()
            result.save(buf, format="PNG")
            return buf.getvalue()

        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, _process),
            timeout=self.timeout
        )

    # ==================== Upscaling ====================

    async def upscale(
        self,
        image_bytes: bytes,
        scale: int = 4,
        preserve_alpha: bool = True
    ) -> UpscaleResult:
        """
        Upscale image using Lanczos resampling.
        Preserves alpha/transparency - critical for DTF printing.

        Args:
            image_bytes: Raw image bytes
            scale: Scale factor (1-8). Default: 4
            preserve_alpha: Keep transparency. Default: True

        Returns:
            UpscaleResult with upscaled image
        """
        start = time.time()
        scale = max(1, min(scale, 8))

        def _process():
            img = Image.open(io.BytesIO(image_bytes))
            orig_size = img.size
            has_alpha = img.mode == "RGBA"

            new_size = (orig_size[0] * scale, orig_size[1] * scale)

            if preserve_alpha and has_alpha:
                result = img.resize(new_size, Image.Resampling.LANCZOS)
            else:
                if img.mode == "RGBA":
                    rgb = Image.new("RGB", img.size, (255, 255, 255))
                    rgb.paste(img, mask=img.split()[3])
                    result = rgb.resize(new_size, Image.Resampling.LANCZOS)
                    has_alpha = False
                else:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    result = img.resize(new_size, Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            result.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), orig_size, new_size, has_alpha

        try:
            loop = asyncio.get_event_loop()
            result_bytes, orig, upscaled, has_alpha = await asyncio.wait_for(
                loop.run_in_executor(_executor, _process),
                timeout=60
            )

            return UpscaleResult(
                success=True,
                image_bytes=result_bytes,
                image_base64=base64.b64encode(result_bytes).decode(),
                original_size=orig,
                upscaled_size=upscaled,
                scale_factor=scale,
                processing_time_ms=(time.time() - start) * 1000,
                has_alpha=has_alpha
            )

        except Exception as e:
            return UpscaleResult(
                success=False,
                error=str(e),
                processing_time_ms=(time.time() - start) * 1000
            )

    # ==================== Utilities ====================

    def get_available_models(self) -> list[dict]:
        """Get list of available models based on configured API keys."""
        available = []
        for model_id, config in MODELS.items():
            provider = config["provider"]
            is_available = True

            if provider == "runware" and not self.runware_key:
                is_available = False
            elif provider == "kie" and not self.kie_key:
                is_available = False

            available.append({
                "id": model_id,
                "name": config["name"],
                "provider": provider,
                "cost": config["cost"],
                "available": is_available,
                "notes": config.get("notes", "")
            })

        return sorted(available, key=lambda x: MODELS[x["id"]]["priority"])

    async def close(self):
        """Clean up connections."""
        if self._runware_client:
            try:
                await self._runware_client.disconnect()
            except Exception:
                pass
            self._runware_client = None
