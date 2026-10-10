from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required by the API and worker; not needed by scripts/run_pipeline.py.
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    storage_bucket: str = "scripts"

    groq_api_key: str | None = None  # the SDK also reads GROQ_API_KEY from the environment
    # Models must support strict JSON-schema output on Groq; the vision model must accept images.
    groq_vision_model: str = "qwen/qwen3.8-27b"      # reads handwriting
    groq_grading_model: str = "openai/gpt-oss-120b"  # segments and grades
    groq_check_model: str = "openai/gpt-oss-120b"    # independent second grading
    max_parallel_calls: int = 4

    # Page reading. "auto" uses Azure AI Document Intelligence when configured, else the vision model.
    ocr_provider: str = "auto"   # auto | azure | groq
    azure_di_endpoint: str = ""
    azure_di_key: str = ""

    def make_reader(self):
        """The OCR reader to use for pages, or None for the Groq vision model."""
        use_azure = self.ocr_provider == "azure" or (
            self.ocr_provider == "auto" and self.azure_di_endpoint and self.azure_di_key)
        if not use_azure:
            return None
        if not (self.azure_di_endpoint and self.azure_di_key):
            raise RuntimeError("OCR_PROVIDER=azure needs AZURE_DI_ENDPOINT and AZURE_DI_KEY in backend/.env")
        from app.ai.ocr_azure import AzureReader
        return AzureReader(self.azure_di_endpoint, self.azure_di_key)

    def page_reader_name(self) -> str:
        """Name of whatever reads pages (labels caches and reports)."""
        if self.make_reader() is not None:
            from app.ai.ocr_azure import MODEL_NAME
            return MODEL_NAME
        return self.groq_vision_model

    render_dpi: int = 150
    worker_poll_seconds: float = 3.0
    max_attempts: int = 3

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# USD per million tokens (input, output), from Groq's model pages. Cached input bills at 0.5x.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.80, 4.00),
}
CACHED_INPUT_FACTOR = 0.5

# Azure Document Intelligence "read": list price per page (first 500 pages/month free on F0).
AZURE_READ_PRICE_PER_PAGE = 1.50 / 1000


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read: int = 0, cache_write: int = 0) -> float:
    """Estimated USD cost. Unknown models are priced at 0 (add them to MODEL_PRICES)."""
    price_in, price_out = MODEL_PRICES.get(model, (0.0, 0.0))
    return (
        (input_tokens + cache_write) * price_in
        + cache_read * price_in * CACHED_INPUT_FACTOR
        + output_tokens * price_out
    ) / 1_000_000
