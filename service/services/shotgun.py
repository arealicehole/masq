"""
Shotgun service for running multiple background removal models in parallel.
Returns results from all models for user selection.
"""

import asyncio
import logging
import time
from typing import Optional

from config import get_settings, get_model_config
from services.providers import (
    BaseProvider,
    ProviderResult,
    ProviderStatus,
    RunwareProvider,
    KieProvider,
    LocalProvider
)

logger = logging.getLogger(__name__)


class ShotgunResult:
    """Container for all shotgun results."""

    def __init__(self):
        self.results: list[ProviderResult] = []
        self.total_time_ms: float = 0.0
        self.total_cost: float = 0.0
        self.successful_count: int = 0
        self.failed_count: int = 0

    def add_result(self, result: ProviderResult):
        """Add a result to the collection."""
        self.results.append(result)
        self.total_cost += result.cost
        if result.is_success:
            self.successful_count += 1
        else:
            self.failed_count += 1

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total_models": len(self.results),
                "successful": self.successful_count,
                "failed": self.failed_count,
                "total_time_ms": self.total_time_ms,
                "total_cost": self.total_cost
            }
        }

    @property
    def successful_results(self) -> list[ProviderResult]:
        """Get only successful results."""
        return [r for r in self.results if r.is_success]


class ShotgunService:
    """
    Service that runs multiple background removal models in parallel.

    The "shotgun" approach fires all models simultaneously and returns
    all results, allowing the user to pick the best one.
    """

    def __init__(self):
        self.settings = get_settings()
        self.model_config = get_model_config()
        self.shotgun_config = self.model_config.shotgun_config
        self._providers: dict[str, BaseProvider] = {}
        self._initialized = False

    def _create_provider(self, model_name: str, model_cfg: dict) -> Optional[BaseProvider]:
        """Create a provider instance for a model."""
        provider_name = model_cfg.get("provider")
        provider_cfg = self.model_config.get_provider_config(provider_name) or {}

        try:
            if provider_name == "runware":
                return RunwareProvider(
                    model_cfg,
                    provider_cfg,
                    self.settings.runware_api_key
                )
            elif provider_name == "kie":
                return KieProvider(
                    model_cfg,
                    provider_cfg,
                    self.settings.kie_api_key
                )
            elif provider_name == "local":
                return LocalProvider(model_cfg, provider_cfg)
            else:
                logger.warning(f"Unknown provider: {provider_name}")
                return None
        except Exception as e:
            logger.error(f"Failed to create provider for {model_name}: {e}")
            return None

    def initialize(self):
        """Initialize all configured providers."""
        if self._initialized:
            return

        enabled_models = self.model_config.get_enabled_bg_models()

        for model_name, model_cfg in enabled_models.items():
            provider = self._create_provider(model_name, model_cfg)
            if provider:
                self._providers[model_name] = provider
                logger.info(f"Initialized provider for: {model_name}")

        self._initialized = True
        logger.info(f"Shotgun service initialized with {len(self._providers)} providers")

    async def _run_single_model(
        self,
        model_name: str,
        provider: BaseProvider,
        image_bytes: bytes
    ) -> ProviderResult:
        """Run a single model and return result."""
        try:
            logger.debug(f"Starting {model_name}...")
            result = await provider.remove_background(image_bytes)
            logger.debug(f"Completed {model_name}: {result.status.value}")
            return result
        except Exception as e:
            logger.exception(f"Unexpected error in {model_name}: {e}")
            return ProviderResult(
                model_name=provider.model_name,
                provider=provider.provider_config.get("connection_type", "unknown"),
                status=ProviderStatus.FAILED,
                error=str(e)
            )

    async def execute(
        self,
        image_bytes: bytes,
        models: Optional[list[str]] = None
    ) -> ShotgunResult:
        """
        Execute background removal with multiple models in parallel.

        Args:
            image_bytes: Raw image bytes to process
            models: Optional list of model names to use. If None, uses default models.

        Returns:
            ShotgunResult containing all results
        """
        self.initialize()

        start_time = time.time()
        shotgun_result = ShotgunResult()

        # Determine which models to run
        if models is None:
            models = self.model_config.get_default_shotgun_models()

        # Filter to only available providers
        active_providers = {
            name: provider
            for name, provider in self._providers.items()
            if name in models
        }

        if not active_providers:
            logger.warning("No providers available for shotgun execution")
            return shotgun_result

        logger.info(f"Executing shotgun with {len(active_providers)} models: {list(active_providers.keys())}")

        # Run in parallel or sequentially based on config
        if self.shotgun_config.get("parallel", True):
            # Run all models in parallel
            tasks = [
                self._run_single_model(name, provider, image_bytes)
                for name, provider in active_providers.items()
            ]

            total_timeout = self.shotgun_config.get("total_timeout", 90)

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=total_timeout
                )

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Task exception: {result}")
                    elif isinstance(result, ProviderResult):
                        shotgun_result.add_result(result)

            except asyncio.TimeoutError:
                logger.warning(f"Shotgun timeout after {total_timeout}s")
        else:
            # Run sequentially
            for name, provider in active_providers.items():
                result = await self._run_single_model(name, provider, image_bytes)
                shotgun_result.add_result(result)

        shotgun_result.total_time_ms = (time.time() - start_time) * 1000

        # Check minimum successful results
        min_successful = self.shotgun_config.get("min_successful", 1)
        if shotgun_result.successful_count < min_successful:
            logger.warning(
                f"Only {shotgun_result.successful_count}/{min_successful} "
                f"minimum successful results"
            )

        logger.info(
            f"Shotgun complete: {shotgun_result.successful_count} successful, "
            f"{shotgun_result.failed_count} failed, "
            f"{shotgun_result.total_time_ms:.0f}ms total"
        )

        return shotgun_result

    async def close(self):
        """Close all provider connections."""
        for name, provider in self._providers.items():
            if hasattr(provider, "close"):
                try:
                    await provider.close()
                except Exception as e:
                    logger.warning(f"Error closing {name}: {e}")


# Singleton instance
_shotgun_service: Optional[ShotgunService] = None


def get_shotgun_service() -> ShotgunService:
    """Get the singleton shotgun service instance."""
    global _shotgun_service
    if _shotgun_service is None:
        _shotgun_service = ShotgunService()
    return _shotgun_service
