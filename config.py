import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TYPESENSE_HOST = os.getenv("TYPESENSE_HOST", "localhost")
    TYPESENSE_PORT = int(os.getenv("TYPESENSE_PORT", 8108))
    TYPESENSE_PROTOCOL = os.getenv("TYPESENSE_PROTOCOL", "http")
    TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "xyz123secret")
    TYPESENSE_COLLECTION_NAME = os.getenv("TYPESENSE_COLLECTION_NAME", "materials")
    
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
    PORT = int(os.getenv("PORT", 8000))

config = Config()