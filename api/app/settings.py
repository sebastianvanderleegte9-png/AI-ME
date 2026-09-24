from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://me:me@localhost:5432/me"
    redis_url: str = "redis://localhost:6379/0"
    api_key: str = "dev-key"  # replaced by real auth (Clerk) in Component 1

    # Provider selection. "fake" implementations exist for every interface so the
    # whole system runs with no external accounts.
    llm_provider: str = "fake"          # fake | anthropic
    enrichment_provider: str = "fake"   # fake | apollo
    social_provider: str = "fake"       # fake | linkedin_x
    anthropic_api_key: str | None = None

    rules_version: str = "v0"

    # SMS surface (Component 13)
    messaging_provider: str = "fake"       # fake | twilio
    transcription_provider: str = "fake"   # fake | whisper
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    openai_api_key: str | None = None
    public_base_url: str = "http://localhost:8000"   # for setup links in texts


settings = Settings()
