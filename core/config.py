import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """No LLM or embedding settings: the LLM is configured in the ElevenLabs Agents Platform."""

    app_env: str = os.getenv("APP_ENV", "dev")
    database_path: str = os.getenv("DATABASE_PATH", "authrelay.db")
    agent_tool_token: str = os.getenv("AGENT_TOOL_TOKEN", "")
    reviewer_token: str = os.getenv("REVIEWER_TOKEN", "")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_agent_id: str = os.getenv("ELEVENLABS_AGENT_ID", "")
    elevenlabs_webhook_secret: str = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")


settings = Settings()
