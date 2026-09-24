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
    # brand (Component 14b). The font is loaded from the privacy-friendly Google Fonts mirror
    # (api.fonts.coollabs.io) so no visitor data reaches Google. Any Google Fonts family works.
    site_name: str = "Aime"
    site_font: str = "Figtree"
    site_font_weights: str = "400;500;600;700;800"
    font_css_base: str = "https://api.fonts.coollabs.io/css2"

    # Onboarding + billing (Component 14)
    billing_provider: str = "fake"          # fake | stripe
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_founder: str | None = None
    stripe_price_team: str | None = None
    stripe_price_growth: str | None = None
    oauth_provider: str = "fake"            # fake | real
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    x_client_id: str | None = None
    x_client_secret: str | None = None
    token_encryption_key: str = "zK3G3ml8tE6a4h0KZ0QW3M4aM9r1vZ8KIhG7z8W2lqg="   # dev only; set a real Fernet key in prod
    ms_client_id: str | None = None
    ms_client_secret: str | None = None
    ms_tenant: str = "common"

    # Calendar + email outreach (Component 15): personalized emails and meeting scheduling
    # over the founder's own Outlook, connected the same way as LinkedIn/X.
    calendar_provider: str = "fake"   # fake | microsoft
    email_provider: str = "fake"      # fake | microsoft


settings = Settings()
