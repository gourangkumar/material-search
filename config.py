import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    TYPESENSE_HOST: str = os.getenv("TYPESENSE_HOST", "localhost")
    TYPESENSE_PORT: int = int(os.getenv("TYPESENSE_PORT", "8108"))
    TYPESENSE_PROTOCOL: str = os.getenv("TYPESENSE_PROTOCOL", "http")
    TYPESENSE_API_KEY: str = os.getenv("TYPESENSE_API_KEY", "xyz123secret")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

config = Config()
