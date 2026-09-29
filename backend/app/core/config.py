from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ev98:ev98@localhost:5433/ev98"
    cors_origins: str = "http://localhost:5173"
    ocm_api_key: str = ""
    abrp_api_key: str = ""
    neshan_api_key: str = ""
    sharinet_base_url: str = "https://gen.emapna.com"
    status_ttl_seconds: int = 900
    ingestion_token: str = ""
    public_site_url: str = "https://ev98.ir"
    frontend_index_path: str = "/var/www/ev98/index.html"

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_BACKEND_ROOT / ".env")),
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
