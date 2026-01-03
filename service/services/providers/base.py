"""
Base provider interface for background removal models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import base64


class ProviderStatus(str, Enum):
    """Status of a provider operation."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass
class ProviderResult:
    """Result from a background removal provider."""
    model_name: str
    provider: str
    status: ProviderStatus
    image_base64: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    cost: float = 0.0
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert result to dictionary for API response."""
        result = {
            "model_name": self.model_name,
            "provider": self.provider,
            "status": self.status.value,
            "processing_time_ms": self.processing_time_ms,
            "cost": self.cost,
            "timestamp": self.timestamp.isoformat()
        }

        if self.status == ProviderStatus.SUCCESS and self.image_base64:
            result["image_base64"] = self.image_base64

        if self.error:
            result["error"] = self.error

        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @property
    def is_success(self) -> bool:
        """Check if the operation was successful."""
        return self.status == ProviderStatus.SUCCESS and self.image_base64 is not None


class BaseProvider(ABC):
    """Abstract base class for background removal providers."""

    def __init__(self, model_config: dict, provider_config: dict):
        """
        Initialize the provider.

        Args:
            model_config: Configuration for the specific model
            provider_config: Configuration for the provider (API keys, endpoints, etc.)
        """
        self.model_config = model_config
        self.provider_config = provider_config
        self.model_name = model_config.get("name", "Unknown")
        self.model_id = model_config.get("model_id", "")
        self.timeout = model_config.get("timeout", 30)
        self.cost_per_image = model_config.get("cost_per_image", 0.0)

    @abstractmethod
    async def remove_background(self, image_bytes: bytes) -> ProviderResult:
        """
        Remove background from an image.

        Args:
            image_bytes: Raw image bytes

        Returns:
            ProviderResult with the processed image or error
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the provider is available and properly configured.

        Returns:
            True if the provider can accept requests
        """
        pass

    def _bytes_to_base64(self, image_bytes: bytes) -> str:
        """Convert image bytes to base64 string."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _base64_to_bytes(self, base64_str: str) -> bytes:
        """Convert base64 string to image bytes."""
        return base64.b64decode(base64_str)

    def _create_error_result(self, error: str, status: ProviderStatus = ProviderStatus.FAILED) -> ProviderResult:
        """Create a standardized error result."""
        return ProviderResult(
            model_name=self.model_name,
            provider=self.provider_config.get("connection_type", "unknown"),
            status=status,
            error=error,
            cost=0.0
        )
