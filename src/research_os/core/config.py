from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
    environment:str="development"; log_level:str="INFO"
    database_url:str="postgresql+psycopg://research_os:research_os@localhost:5433/research_os"
    bybit_api_key:str=""; bybit_api_secret:str=""
    telegram_bot_token:str=""; telegram_chat_id:str=""
    signal_min_probability:float=Field(default=.70,ge=0,le=1); signal_min_ev:float=0.0
    report_timezone:str="Europe/Moscow"; report_hour:int=20; report_minute:int=0
@lru_cache
def get_settings()->Settings: return Settings()
