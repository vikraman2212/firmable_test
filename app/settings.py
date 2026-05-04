"""Runtime configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    opensearch_url: str = "http://localhost:9200"
    index_name: str = "companies"
    default_page_size: int = 20
    max_page_size: int = 100


settings = Settings()
