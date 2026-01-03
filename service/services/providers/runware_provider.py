"""
Runware API provider for background removal.
Uses WebSocket connection for RMBG 2.0 and BiRefNet models.
"""

import asyncio
import base64
import logging
import time
from typing import Optional

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger(__name__)


class RunwareProvider(BaseProvider):
    """
    Provider for Runware API background removal.

    Supports models:
    - runware:110@1 (RMBG 2.0)
    - runware:112@10 (BiRefNet Portrait)
    """

    def __init__(self, model_config: dict, provider_config: dict, api_key: str):
        super().__init__(model_config, provider_config)
        self.api_key = api_key
        self._runware = None

    async def _get_client(self):
        """Get or create Runware client."""
        if self._runware is None:
            try:
                from runware import Runware
                self._runware = Runware(api_key=self.api_key)
                await self._runware.connect()
            except Exception as e:
                logger.error(f"Failed to connect to Runware: {e}")
                raise
        return self._runware

    async def is_available(self) -> bool:
        """Check if Runware API is available."""
        if not self.api_key:
            return False
        try:
            await self._get_client()
            return True
        except Exception as e:
            logger.warning(f"Runware not available: {e}")
            return False

    async def remove_background(self, image_bytes: bytes) -> ProviderResult:
        """
        Remove background using Runware API.

        Args:
            image_bytes: Raw image bytes

        Returns:
            ProviderResult with processed image
        """
        start_time = time.time()

        if not self.api_key:
            return self._create_error_result(
                "Runware API key not configured",
                ProviderStatus.UNAVAILABLE
            )

        try:
            runware = await self._get_client()

            # Convert image to base64 data URI
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            image_data_uri = f"data:image/png;base64,{image_base64}"

            # Call Runware background removal
            from runware import IImageBackgroundRemoval

            request = IImageBackgroundRemoval(
                inputImage=image_data_uri,
                model=self.model_id,
                outputFormat="PNG"
            )

            results = await asyncio.wait_for(
                runware.imageBackgroundRemoval(request),
                timeout=self.timeout
            )

            if not results or len(results) == 0:
                return self._create_error_result("No results returned from Runware")

            result = results[0]
            processing_time = (time.time() - start_time) * 1000

            # Get the result image
            if hasattr(result, "imageURL") and result.imageURL:
                # Fetch the image from URL
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(result.imageURL)
                    response.raise_for_status()
                    result_bytes = response.content
                    result_base64 = base64.b64encode(result_bytes).decode("utf-8")
            elif hasattr(result, "imageBase64") and result.imageBase64:
                result_base64 = result.imageBase64
            else:
                return self._create_error_result("No image in Runware response")

            return ProviderResult(
                model_name=self.model_name,
                provider="runware",
                status=ProviderStatus.SUCCESS,
                image_base64=result_base64,
                processing_time_ms=processing_time,
                cost=self.cost_per_image,
                metadata={
                    "model_id": self.model_id,
                    "task_uuid": getattr(result, "taskUUID", None)
                }
            )

        except asyncio.TimeoutError:
            return self._create_error_result(
                f"Runware timeout after {self.timeout}s",
                ProviderStatus.TIMEOUT
            )
        except Exception as e:
            logger.exception(f"Runware error: {e}")
            return self._create_error_result(str(e))

    async def close(self):
        """Close the Runware connection."""
        if self._runware is not None:
            try:
                await self._runware.disconnect()
            except Exception as e:
                logger.warning(f"Error closing Runware connection: {e}")
            finally:
                self._runware = None
