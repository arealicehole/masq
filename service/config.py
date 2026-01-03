"""
Configuration management for the image processing service.
Loads settings from environment variables and config/models.yaml
"""

import os
from pathlib import Path
from typing import Any
from functools import lru_cache

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    runware_api_key: str = Field(default="", alias="RUNWARE_API_KEY")
    kie_api_key: str = Field(default="", alias="KIE_API_KEY")

    # Server settings
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_concurrent_jobs: int = Field(default=4, alias="MAX_CONCURRENT_JOBS")
    uvicorn_workers: int = Field(default=2, alias="UVICORN_WORKERS")

    # Timeouts (seconds)
    request_timeout: int = Field(default=60, alias="REQUEST_TIMEOUT")
    runware_timeout: int = Field(default=120, alias="RUNWARE_TIMEOUT")
    kie_timeout: int = Field(default=120, alias="KIE_TIMEOUT")

    # Storage
    temp_dir: str = Field(default="/tmp/img-proc", alias="TEMP_DIR")
    cleanup_after_seconds: int = Field(default=300, alias="CLEANUP_AFTER_SECONDS")

    # Upload limits
    max_upload_size: int = Field(default=52428800, alias="MAX_UPLOAD_SIZE")  # 50MB

    # Model configuration file path
    models_config_path: str = Field(
        default="config/models.yaml",
        alias="MODELS_CONFIG_PATH"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class ModelConfig:
    """Loads and provides access to model configurations from YAML."""

    def __init__(self, config_path: str = "config/models.yaml"):
        self.config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            self._config = yaml.safe_load(f)

    @property
    def background_removal_models(self) -> dict[str, dict]:
        """Get all background removal model configurations."""
        return self._config.get("background_removal", {})

    @property
    def upscaling_models(self) -> dict[str, dict]:
        """Get all upscaling model configurations."""
        return self._config.get("upscaling", {})

    @property
    def providers(self) -> dict[str, dict]:
        """Get provider configurations."""
        return self._config.get("providers", {})

    @property
    def shotgun_config(self) -> dict[str, Any]:
        """Get shotgun execution configuration."""
        return self._config.get("shotgun", {})

    def get_enabled_bg_models(self) -> dict[str, dict]:
        """Get only enabled background removal models."""
        return {
            name: config
            for name, config in self.background_removal_models.items()
            if config.get("enabled", True)
        }

    def get_default_shotgun_models(self) -> list[str]:
        """Get the default list of models for shotgun execution."""
        return self.shotgun_config.get("default_models", [])

    def get_model_by_name(self, name: str) -> dict | None:
        """Get a specific model configuration by name."""
        if name in self.background_removal_models:
            return self.background_removal_models[name]
        if name in self.upscaling_models:
            return self.upscaling_models[name]
        return None

    def get_provider_config(self, provider: str) -> dict | None:
        """Get configuration for a specific provider."""
        return self.providers.get(provider)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


@lru_cache()
def get_model_config() -> ModelConfig:
    """Get cached model configuration instance."""
    settings = get_settings()
    return ModelConfig(settings.models_config_path)
