import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./ledger.db"
    app_encryption_key: str = ""
    storage_dir: Path = Path("./data/uploads")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    deepseek_base_url: str = "https://api.deepseek.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def fernet(self) -> Fernet:
        secret = self.app_encryption_key or "ledger-study-dev-key-change-me"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)


settings = Settings()
