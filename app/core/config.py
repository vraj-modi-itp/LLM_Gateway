from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Intelligent LLM Proxy"
    PORT: int = 8000
    GEMINI_API_KEY: str
    GROQ_API_KEY: str
    
    # Ollama variables pointing to local instance and Gemma
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1/chat/completions"
    OLLAMA_MODEL: str = "gemma:2b"

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()