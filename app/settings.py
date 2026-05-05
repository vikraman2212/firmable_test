"""Runtime configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    opensearch_url: str = "http://localhost:9200"
    index_name: str = "companies"
    search_template_id: str = "firmable-search-hybrid-v1"
    keyword_search_template_id: str = "firmable-search-v1"
    hybrid_search_pipeline: str = "hybrid-search-pipeline"
    embedding_model_id: str = ""
    embedding_model_state_file: str = "/tmp/firmable-ml/model_id"
    hybrid_neural_k: int = 100
    default_page_size: int = 20
    max_page_size: int = 100

    # Ollama LLM backend
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout: int = 30

    # Tavily web search (optional; when empty the agent falls back to DuckDuckGo)
    tavily_api_key: str = ""

    # LangSmith tracing (optional)
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""

    # Structured logging
    log_opensearch_enabled: bool = False
    log_opensearch_url: str = ""  # defaults to opensearch_url when empty
    log_level: str = "INFO"

    @property
    def effective_log_opensearch_url(self) -> str:
        return self.log_opensearch_url or self.opensearch_url

    @property
    def effective_embedding_model_id(self) -> str:
        if self.embedding_model_id:
            return self.embedding_model_id

        state_file = Path(self.embedding_model_state_file)
        if not state_file.is_file():
            return ""

        return state_file.read_text(encoding="utf-8").strip()


settings = Settings()
