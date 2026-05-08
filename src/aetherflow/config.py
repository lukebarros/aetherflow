"""Configuration management using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_url: str = "postgresql://aetherflow:aetherflow_dev@localhost:5432/aetherflow"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Environment
    env: str = "development"
    log_level: str = "INFO"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Worker
    worker_concurrency: int = 1
    worker_timeout_seconds: int = 3600
    worker_heartbeat_interval: int = 10
    
    # Task execution
    max_task_retries: int = 3
    initial_retry_delay_seconds: int = 1
    max_retry_delay_seconds: int = 300
    
    class Config:
        """Pydantic config."""
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
