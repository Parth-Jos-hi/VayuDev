from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
class Settings(BaseSettings):
    name: str = "VayuDev"
    version: str = "0.1"
    debug: bool = Field(default=False)
    environment: str = Field(default="development")
    database_url: SecretStr
    supabase_url:str
    supabase_jwt_issuer:str
    supabase_jwks_url:str
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
settings = Settings()