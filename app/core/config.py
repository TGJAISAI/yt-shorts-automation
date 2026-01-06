"""Configuration management for the application."""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# Load environment variables
load_dotenv()


class ScriptGenerationConfig(BaseModel):
    """Configuration for script generation."""
    model: str
    max_tokens: int
    temperature: float
    niche: str
    num_scenes: int
    target_duration_seconds: int
    max_word_count: int
    min_word_count: int


class VideoGenerationConfig(BaseModel):
    """Configuration for video generation."""
    provider: str
    max_parallel_clips: int
    max_retries: int
    timeout_seconds: int


class AudioGenerationConfig(BaseModel):
    """Configuration for audio generation."""
    provider: str
    voice: str
    model: str
    speed: float
    format: str


class YouTubeUploadConfig(BaseModel):
    """Configuration for YouTube uploads."""
    category_id: str
    privacy_status: str
    default_tags: list[str]
    made_for_kids: bool
    default_language: str
    default_description_suffix: str


class FileRetentionConfig(BaseModel):
    """Configuration for file retention."""
    keep_days: int
    max_storage_gb: int
    auto_cleanup: bool


class RetryConfig(BaseModel):
    """Configuration for retry logic."""
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int
    exponential_base: int


class LoggingConfig(BaseModel):
    """Configuration for logging."""
    format: str
    date_format: str
    file_rotation: str
    backup_count: int


class AppConfig(BaseModel):
    """Main application configuration."""
    name: str
    version: str
    description: str


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # OpenAI API
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    # Gemini API
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")

    # Pexels API
    pexels_api_key: str = Field(..., env="PEXELS_API_KEY")

    # ElevenLabs API
    elevenlabs_api_key: str = Field(..., env="ELEVENLABS_API_KEY")

    # YouTube API
    youtube_client_id: str = Field(..., env="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(..., env="YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token: str = Field(..., env="YOUTUBE_REFRESH_TOKEN")

    # Application
    environment: str = Field(default="production", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    data_dir: str = Field(..., env="DATA_DIR")
    models_dir: str = Field(..., env="MODELS_DIR")

    # Scheduling
    schedule_enabled: bool = Field(default=True, env="SCHEDULE_ENABLED")
    schedule_interval_hours: int = Field(default=8, env="SCHEDULE_INTERVAL_HOURS")

    # Video Settings
    video_width: int = Field(default=1080, env="VIDEO_WIDTH")
    video_height: int = Field(default=1920, env="VIDEO_HEIGHT")
    max_video_duration: int = Field(default=59, env="MAX_VIDEO_DURATION")

    class Config:
        env_file = ".env"
        case_sensitive = False


class Config:
    """Central configuration class."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration.

        Args:
            config_path: Path to config.yaml file. Defaults to config.yaml in project root.
        """
        # Load environment settings
        self.settings = Settings()

        # Load YAML configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config.yaml"

        with open(config_path, 'r') as f:
            self.yaml_config: Dict[str, Any] = yaml.safe_load(f)

        # Parse configuration sections
        self.app = AppConfig(**self.yaml_config.get('app', {}))
        self.script_generation = ScriptGenerationConfig(**self.yaml_config.get('script_generation', {}))
        self.video_generation = VideoGenerationConfig(**self.yaml_config.get('video_generation', {}))
        self.audio_generation = AudioGenerationConfig(**self.yaml_config.get('audio_generation', {}))
        self.youtube_upload = YouTubeUploadConfig(**self.yaml_config.get('youtube_upload', {}))
        self.file_retention = FileRetentionConfig(**self.yaml_config.get('file_retention', {}))
        self.retry = RetryConfig(**self.yaml_config.get('retry', {}))
        self.logging = LoggingConfig(**self.yaml_config.get('logging', {}))

        # Create necessary directories
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure all necessary directories exist."""
        directories = [
            self.settings.data_dir,
            self.settings.models_dir,
            Path(self.settings.data_dir) / "outputs" / "scripts",
            Path(self.settings.data_dir) / "outputs" / "images",
            Path(self.settings.data_dir) / "outputs" / "audio",
            Path(self.settings.data_dir) / "outputs" / "videos",
            Path(self.settings.data_dir) / "prompts",
            Path(self.settings.data_dir) / "metadata",
            "logs",
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def get_project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent

    def validate(self) -> bool:
        """Validate configuration."""
        try:
            # Check required environment variables
            assert self.settings.openai_api_key, "OPENAI_API_KEY is required"
            assert self.settings.gemini_api_key, "GEMINI_API_KEY is required"
            assert self.settings.youtube_client_id, "YOUTUBE_CLIENT_ID is required"
            assert self.settings.youtube_client_secret, "YOUTUBE_CLIENT_SECRET is required"

            # Check directories exist
            assert Path(self.settings.data_dir).exists(), f"Data directory {self.settings.data_dir} does not exist"

            # Check video dimensions for Shorts
            assert self.settings.video_width == 1080, "Video width must be 1080 for YouTube Shorts"
            assert self.settings.video_height == 1920, "Video height must be 1920 for YouTube Shorts"
            assert self.settings.max_video_duration < 60, "Max duration must be less than 60s for YouTube Shorts"

            return True
        except AssertionError as e:
            raise ValueError(f"Configuration validation failed: {e}")


# Global configuration instance
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get or create global configuration instance.

    Args:
        config_path: Optional path to config.yaml file.

    Returns:
        Config instance.
    """
    global _config
    if _config is None:
        _config = Config(config_path)
        _config.validate()
    return _config


def reset_config():
    """Reset global configuration instance (mainly for testing)."""
    global _config
    _config = None
