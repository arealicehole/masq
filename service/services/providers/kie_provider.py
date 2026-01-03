"""
Kie.ai API provider for background removal.
Uses REST API with CDN upload for Recraft model.
"""

import asyncio
import base64
import logging
import time
from typing import Optional

import httpx

from .base import BaseProvider, ProviderResult, ProviderStatus

logger = logging.getLogger(__name__)


class KieProvider(BaseProvider):
    """
    Provider for Kie.ai API background removal.

    Supports models:
    - recraft/remove-background
    """

    def __init__(self, model_config: dict, provider_config: dict, api_key: str):
        super().__init__(model_config, provider_config)
        self.api_key = api_key
        self.base_url = provider_config.get("base_url", "https://api.kie.ai/api/v1")
        self.upload_endpoint = provider_config.get(
            "upload_endpoint",
            "https://kieai.redpandaai.co/api/file-stream-upload"
        )
        self.poll_interval = provider_config.get("poll_interval", 2)
        self.max_poll_attempts = provider_config.get("max_poll_attempts", 60)

    async def is_available(self) -> bool:
        """Check if Kie.ai API is available."""
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient() as client:
                # Simple health check
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=5.0
                )
                return response.status_code in [200, 404]  # 404 means endpoint exists but path wrong
        except Exception as e:
            logger.warning(f"Kie.ai not available: {e}")
            return True  # Assume available if we can't check

    async def _upload_to_cdn(self, client: httpx.AsyncClient, image_bytes: bytes) -> str:
        """Upload image to Kie.ai CDN and return URL."""
        response = await client.post(
            self.upload_endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": ("image.png", image_bytes, "image/png")},
            data={"uploadPath": "masq-uploads"},
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            raise ValueError(f"CDN upload failed: {data}")

        # Extract CDN URL from response
        file_url = data.get("data", {}).get("downloadUrl") or data.get("data", {}).get("fileUrl") or data.get("data", {}).get("url")
        if not file_url:
            raise ValueError(f"No URL in CDN upload response: {data}")
        return file_url

    async def _submit_task(self, client: httpx.AsyncClient, image_url: str) -> str:
        """Submit background removal task and return task ID."""
        response = await client.post(
            f"{self.base_url}/jobs/createTask",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model_id,
                "input": {
                    "image": image_url
                }
            },
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

        if not data or data.get("code") != 200:
            raise ValueError(f"Kie API error: {data}")
        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise ValueError(f"No taskId in response: {data}")
        return task_id

    async def _poll_task(self, client: httpx.AsyncClient, task_id: str) -> dict:
        """Poll for task completion and return result."""
        for _ in range(self.max_poll_attempts):
            response = await client.get(
                f"{self.base_url}/jobs/recordInfo",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"taskId": task_id},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            task_data = data.get("data", {})
            state = task_data.get("state", "").lower()

            if state == "success":
                return task_data
            elif state == "fail":
                raise ValueError(f"Task failed: {task_data.get('failMsg', 'Unknown error')}")

            await asyncio.sleep(self.poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete in time")

    async def _download_result(self, client: httpx.AsyncClient, result_url: str) -> bytes:
        """Download the result image."""
        response = await client.get(result_url, timeout=30.0)
        response.raise_for_status()
        return response.content

    async def remove_background(self, image_bytes: bytes) -> ProviderResult:
        """
        Remove background using Kie.ai API.

        Args:
            image_bytes: Raw image bytes

        Returns:
            ProviderResult with processed image
        """
        start_time = time.time()

        if not self.api_key:
            return self._create_error_result(
                "Kie.ai API key not configured",
                ProviderStatus.UNAVAILABLE
            )

        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Upload image to CDN
                logger.debug(f"Uploading image to Kie.ai CDN...")
                image_url = await self._upload_to_cdn(client, image_bytes)
                logger.debug(f"Image uploaded: {image_url}")

                # Step 2: Submit task
                logger.debug(f"Submitting task with model: {self.model_id}")
                task_id = await self._submit_task(client, image_url)
                logger.debug(f"Task submitted: {task_id}")

                # Step 3: Poll for completion
                result = await asyncio.wait_for(
                    self._poll_task(client, task_id),
                    timeout=self.timeout
                )

                # Step 4: Download result - resultJson is a JSON string
                import json
                result_json_str = result.get("resultJson", "{}")
                result_json = json.loads(result_json_str)
                result_urls = result_json.get("resultUrls", [])
                if not result_urls:
                    raise ValueError(f"No resultUrls in Kie response: {result}")
                result_url = result_urls[0]

                result_bytes = await self._download_result(client, result_url)
                result_base64 = base64.b64encode(result_bytes).decode("utf-8")

                processing_time = (time.time() - start_time) * 1000

                return ProviderResult(
                    model_name=self.model_name,
                    provider="kie",
                    status=ProviderStatus.SUCCESS,
                    image_base64=result_base64,
                    processing_time_ms=processing_time,
                    cost=self.cost_per_image,
                    metadata={
                        "model_id": self.model_id,
                        "task_id": task_id
                    }
                )

        except asyncio.TimeoutError:
            return self._create_error_result(
                f"Kie.ai timeout after {self.timeout}s",
                ProviderStatus.TIMEOUT
            )
        except Exception as e:
            logger.exception(f"Kie.ai error: {e}")
            return self._create_error_result(str(e))
