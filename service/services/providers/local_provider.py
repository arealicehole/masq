"""
Local provider for background removal using rembg.
Runs BiRefNet and ISNet models locally on CPU.
"""

import asyncio
import base64
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PIL import Image

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger(__name__)

# Thread pool for running CPU-bound operations
_executor = ThreadPoolExecutor(max_workers=2)


class LocalProvider(BaseProvider):
    """
    Provider for local background removal using rembg.

    Supports models:
    - birefnet-general
    - isnet-general-use
    """

    def __init__(self, model_config: dict, provider_config: dict):
        super().__init__(model_config, provider_config)
        self._session = None
        self._model_loaded = False

    def _get_session(self):
        """Get or create rembg session for this model."""
        if self._session is None:
            from rembg import new_session
            logger.info(f"Loading local model: {self.model_id}")
            self._session = new_session(self.model_id)
            self._model_loaded = True
            logger.info(f"Model loaded: {self.model_id}")
        return self._session

    async def is_available(self) -> bool:
        """Check if local models are available."""
        try:
            # Try to import rembg
            import rembg
            return True
        except ImportError:
            logger.warning("rembg not installed")
            return False

    def _remove_background_sync(self, image_bytes: bytes) -> bytes:
        """Synchronous background removal for thread pool."""
        from rembg import remove

        session = self._get_session()

        # Load image
        input_image = Image.open(io.BytesIO(image_bytes))

        # Remove background
        output_image = remove(input_image, session=session)

        # Convert to PNG bytes
        output_buffer = io.BytesIO()
        output_image.save(output_buffer, format="PNG")
        return output_buffer.getvalue()

    async def remove_background(self, image_bytes: bytes) -> ProviderResult:
        """
        Remove background using local rembg model.

        Args:
            image_bytes: Raw image bytes

        Returns:
            ProviderResult with processed image
        """
        start_time = time.time()

        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result_bytes = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    self._remove_background_sync,
                    image_bytes
                ),
                timeout=self.timeout
            )

            result_base64 = base64.b64encode(result_bytes).decode("utf-8")
            processing_time = (time.time() - start_time) * 1000

            return ProviderResult(
                model_name=self.model_name,
                provider="local",
                status=ProviderStatus.SUCCESS,
                image_base64=result_base64,
                processing_time_ms=processing_time,
                cost=0.0,  # Local models are free
                metadata={
                    "model_id": self.model_id
                }
            )

        except asyncio.TimeoutError:
            return self._create_error_result(
                f"Local model timeout after {self.timeout}s",
                ProviderStatus.TIMEOUT
            )
        except Exception as e:
            logger.exception(f"Local model error: {e}")
            return self._create_error_result(str(e))

    def preload_model(self):
        """Preload the model into memory."""
        if not self._model_loaded:
            self._get_session()
