from typing import Annotated

import annotated_types
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(env_prefix="DUDEN_")

    api_key: str | None = Field(default=None)

    cli_verbosity: Annotated[
        int, annotated_types.Ge(0), annotated_types.Le(3)
    ] = Field(default=3)


CONFIG = Config()
