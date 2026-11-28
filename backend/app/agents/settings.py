"""Settings for the agents. Reads the same root .env file as the backend (never committed)."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import ROOT_DIR


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_s: float = 60.0


agent_settings = AgentSettings()