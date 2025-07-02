from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(env_prefix="DUDEN_")

    api_key: str
