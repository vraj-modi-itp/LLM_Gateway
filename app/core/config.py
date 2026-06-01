from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Intelligent LLM Proxy"
    PORT: int = 8000
    GEMINI_API_KEY: str
    GROQ_API_KEY: str

    # Tell Pydantic to read from the local .env file and ignore other system env vars
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # This safely bypasses any other stray system environment variables
    )

settings = Settings()