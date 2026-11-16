from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./enterprise_ai.db"
    jwt_secret: str = "insecure-development-secret-change-me"
    access_token_minutes: int = 45
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 25
    bootstrap_email: str = "admin@example.com"
    bootstrap_password: str = "change-this-password"

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env.lower() == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret == "insecure-development-secret-change-me":
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters")
            if self.bootstrap_password == "change-this-password":
                raise ValueError("Production must not use the development bootstrap password")
        return self

settings = Settings()
