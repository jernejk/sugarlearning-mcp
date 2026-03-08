from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    base_url: str = "https://my.sugarlearning.com"
    company_code: str = ""
    user_id: str = ""
    identity_authority: str = "https://identity.ssw.com.au"
    client_id: str = "ssw-sugarlearning-client"
    redirect_uri: str = "http://localhost:8912/callback"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sugarlearning"

    model_config = {"env_prefix": "SL_", "env_file": ".env"}

    @property
    def token_path(self) -> Path:
        p = Path.home() / ".config" / "sugarlearning-tools" / "tokens.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_dir(self) -> Path:
        p = Path(__file__).resolve().parent.parent.parent / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def snapshots_dir(self) -> Path:
        p = self.data_dir / "snapshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def diffs_dir(self) -> Path:
        p = self.data_dir / "diffs"
        p.mkdir(parents=True, exist_ok=True)
        return p


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
