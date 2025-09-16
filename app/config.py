from pydantic_settings import BaseSettings
from pydantic import ConfigDict
import os
from pathlib import Path

# Get the directory where config.py is located
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=str(BASE_DIR / ".env"), 
        env_file_encoding='utf-8'
    )
    
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 3
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str
    azure_openai_deployment_name: str
    azure_openai_embedding_deployment_name: str
    admin_email: str 
    admin_password: str

settings = Settings()