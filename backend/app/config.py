import base64
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./ledger.db"
    app_encryption_key: str = ""
    storage_dir: Path = Path("./data/uploads")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    deepseek_base_url: str = "https://api.deepseek.com"
    max_upload_bytes: int = 50 * 1024 * 1024
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_cache_dir: Path = Path("/data/models")
    worker_poll_seconds: float = 1.0
    backup_dir: Path = Path("/data/backups")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def fernet(self) -> Fernet:
        secret = self.app_encryption_key.strip()
        if not secret or secret == "replace-with-a-fernet-key":
            key_file = self.storage_dir / ".master.key"
            key_file.parent.mkdir(parents=True, exist_ok=True)
            if key_file.exists():
                secret = key_file.read_text(encoding="utf-8").strip()
            else:
                secret = secrets.token_urlsafe(48)
                key_file.write_text(secret, encoding="utf-8")
                os.chmod(key_file, 0o600)
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)

    def decrypt_secret(self, token: str) -> tuple[str, str | None]:
        """读取当前密文，并把旧版固定密钥密文转换为安全密文。"""
        try:
            return self.fernet().decrypt(token.encode()).decode(), None
        except InvalidToken:
            legacy_key = base64.urlsafe_b64encode(hashlib.sha256(b"ledger-study-dev-key-change-me").digest())
            plaintext = Fernet(legacy_key).decrypt(token.encode()).decode()
            return plaintext, self.fernet().encrypt(plaintext.encode()).decode()


settings = Settings()
