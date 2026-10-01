from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import BigInteger, Boolean, DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from research_os.database.base import Base
class _TimeSeriesBase(Base):
    __abstract__=True
    id: Mapped[int]=mapped_column(BigInteger,primary_key=True,autoincrement=True)
    event_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),primary_key=True)
    ingestion_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    point_in_time_available_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    symbol: Mapped[str]=mapped_column(String(32),nullable=False)
    source: Mapped[str]=mapped_column(String(64),nullable=False)
    raw_event_id: Mapped[int|None]=mapped_column(BigInteger,index=True)
class Trade(_TimeSeriesBase):
    __tablename__="trades"; __table_args__=(Index("ix_market_trades_symbol_time","symbol","event_time"),{"schema":"market"})
    exchange_trade_id: Mapped[str|None]=mapped_column(String(128))
    price: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); size: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); side: Mapped[str]=mapped_column(String(16),nullable=False)
class OrderBookUpdate(_TimeSeriesBase):
    __tablename__="orderbook_updates"; __table_args__=(Index("ix_market_ob_updates_symbol_time","symbol","event_time"),{"schema":"market"})
    update_id: Mapped[int]=mapped_column(BigInteger,nullable=False); sequence: Mapped[int|None]=mapped_column(BigInteger); side: Mapped[str]=mapped_column(String(8),nullable=False); price: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); size: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); action: Mapped[str]=mapped_column(String(16),nullable=False)
class OrderBookSnapshot(_TimeSeriesBase):
    __tablename__="orderbook_snapshots"; __table_args__=(Index("ix_market_ob_snapshots_symbol_time","symbol","event_time"),{"schema":"market"})
    update_id: Mapped[int]=mapped_column(BigInteger,nullable=False); sequence: Mapped[int|None]=mapped_column(BigInteger); bids: Mapped[list[dict[str,Any]]]=mapped_column(JSONB,nullable=False); asks: Mapped[list[dict[str,Any]]]=mapped_column(JSONB,nullable=False); valid: Mapped[bool]=mapped_column(Boolean,nullable=False)
class MarketSnapshot(_TimeSeriesBase):
    __tablename__="market_snapshots"; __table_args__=(Index("ix_market_snapshots_symbol_time","symbol","event_time"),{"schema":"market"})
    last_price: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); bid: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); ask: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); mid_price: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); spread: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); volume_24h: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); open_interest: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); funding_rate: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); orderbook_valid: Mapped[bool|None]=mapped_column(Boolean)
class Candle(Base):
    __tablename__="candles"; __table_args__=(Index("ix_market_candles_symbol_interval_time","symbol","interval","event_time"),{"schema":"market"})
    symbol: Mapped[str]=mapped_column(String(32),primary_key=True); interval: Mapped[str]=mapped_column(String(16),primary_key=True); event_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),primary_key=True); ingestion_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); point_in_time_available_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); open: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); high: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); low: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); close: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); volume: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); turnover: Mapped[Decimal|None]=mapped_column(Numeric(38,18)); source: Mapped[str]=mapped_column(String(64),nullable=False); raw_event_id: Mapped[int|None]=mapped_column(BigInteger,index=True)
