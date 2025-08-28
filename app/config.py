from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str
    azure_openai_deployment_name: str
    
    class Config:
        env_file = ".env"
        
settings = Settings()