from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    database_url: str = "sqlite:///./negotiation_brain.db"
    cors_origin: str = "http://localhost:5173"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_from: str = "NegotiationBrain <no-reply@negotiationbrain.ai>"

    frontend_url: str = "http://localhost:5173"
    claude_model: str = "claude-sonnet-4-6"
    max_rounds: int = 8

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
