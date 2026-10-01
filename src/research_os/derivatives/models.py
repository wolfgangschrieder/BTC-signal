from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger,DateTime,Index,Numeric,String
from sqlalchemy.orm import Mapped,mapped_column
from research_os.database.base import Base
class _Derivative(Base):
    __abstract__=True
    id: Mapped[int]=mapped_column(BigInteger,primary_key=True,autoincrement=True); event_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),primary_key=True); ingestion_time: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); point_in_time_available_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); symbol: Mapped[str]=mapped_column(String(32),nullable=False); source: Mapped[str]=mapped_column(String(64),nullable=False); raw_event_id: Mapped[int|None]=mapped_column(BigInteger,index=True)
class FundingRate(_Derivative):
    __tablename__="funding_rates"; __table_args__=(Index("ix_derivatives_funding_symbol_time","symbol","event_time"),{"schema":"derivatives"}); funding_rate: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); funding_time: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class OpenInterest(_Derivative):
    __tablename__="open_interest"; __table_args__=(Index("ix_derivatives_oi_symbol_time","symbol","event_time"),{"schema":"derivatives"}); open_interest: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False)
class Liquidation(_Derivative):
    __tablename__="liquidations"; __table_args__=(Index("ix_derivatives_liq_symbol_time","symbol","event_time"),{"schema":"derivatives"}); side: Mapped[str]=mapped_column(String(16),nullable=False); price: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False); size: Mapped[Decimal]=mapped_column(Numeric(38,18),nullable=False)
