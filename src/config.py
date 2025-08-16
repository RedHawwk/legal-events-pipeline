import os
from pydantic import BaseModel
from dotenv import load_dotenv

# load environment variables from .env
load_dotenv()

class Settings(BaseModel):
    USE_OCR: bool = os.getenv("USE_OCR", "false").lower() == "true"
    USE_LLM: bool = os.getenv("USE_LLM", "false").lower() == "true"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    LLM_MAX_CALL_RATE: int = int(os.getenv("LLM_MAX_CALL_RATE", "4"))
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Create a global settings instance you can import everywhere
settings = Settings()
