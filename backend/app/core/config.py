from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
class Settings(BaseSettings):
    name: str = "VayuDev"
    version: str = "0.1"
    debug: bool = Field(default=False)
    environment: str = Field(default="development")
    database_url: SecretStr
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
settings = Settings()