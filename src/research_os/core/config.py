from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
    environment:str="development"; log_level:str="INFO"
    database_url:str="postgresql+psycopg://research_os:research_os@localhost:5433/research_os"
    bybit_api_key:str=""; bybit_api_secret:str=""
    telegram_bot_token:str=""; telegram_chat_id:str=""
    raw_retention_hours:int=Field(default=0,ge=0)
    signal_emission_enabled:bool=True
    signal_min_probability:float=Field(default=.70,ge=0,le=1); signal_min_ev:float=0.0
    signal_guard_max_latency_ms:float=500.0
    signal_guard_max_spread_bps:float=10.0
    signal_guard_max_orderbook_age_ms:int=5000
    live_history_minutes:int=Field(default=10080,ge=8640)
    calibration_model_ids:str=""
    calibration_max_age_days:int=Field(default=30,ge=1)
    execution_fee_bps:float=Field(default=0.0,ge=0)
    execution_slippage_bps:float=Field(default=0.0,ge=0)
    report_timezone:str="Europe/Moscow"; report_hour:int=20; report_minute:int=0
    fred_api_key:str=""
    cross_market_enabled:bool=False
    cross_market_max_event_skew_seconds:float=300.0
    cross_market_max_source_latency_skew_seconds:float=30.0
@lru_cache
def get_settings()->Settings: return Settings()
