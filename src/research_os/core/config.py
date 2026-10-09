from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
    environment:str="development"; log_level:str="INFO"
    database_url:str="postgresql+psycopg://research_os:research_os@localhost:5433/research_os"
    bybit_api_key:str=""; bybit_api_secret:str=""
    telegram_bot_token:str=""; telegram_chat_id:str=""
    raw_retention_hours:int=Field(default=0,ge=0)
    storage_path:str=""
    storage_max_database_gb:float=Field(default=18,gt=0)
    storage_min_free_gb:float=Field(default=5,gt=0)
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
    deepseek_api_key:SecretStr=Field(default=SecretStr(""),repr=False)
    auditor_enabled:bool=False
    auditor_model:str=Field(default="deepseek-flash",min_length=1,max_length=64,pattern=r"^deepseek-[A-Za-z0-9_-]+$")
    auditor_daily_token_budget:int=Field(default=1_000_000,ge=20_000,le=20_000_000)
    auditor_max_output_tokens:int=Field(default=2200,ge=500,le=3000)
    auditor_retention_days:int=Field(default=7,ge=2,le=14)
    auditor_telegram_enabled:bool=True
    fred_api_key:str=""
    cross_market_enabled:bool=False
    cross_market_refresh_seconds:int=Field(default=60,ge=10)
    cross_market_cache_max_age_seconds:int=Field(default=120,ge=10)
    cross_market_max_event_age_days:int=Field(default=7,ge=1,le=14)
    cross_market_max_event_skew_seconds:float=300.0
    cross_market_max_source_latency_skew_seconds:float=30.0
@lru_cache
def get_settings()->Settings: return Settings()
