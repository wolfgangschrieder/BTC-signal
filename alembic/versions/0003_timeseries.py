"""normalized market and derivatives time-series
Revision ID: 0003_timeseries
Revises: 0002_ingestion
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0003_timeseries"; down_revision="0002_ingestion"; branch_labels=None; depends_on=None

def _base_table(name):
    return [sa.Column("id",sa.BigInteger(),sa.Identity(),primary_key=True),sa.Column("event_time",sa.DateTime(timezone=True),primary_key=True),sa.Column("ingestion_time",sa.DateTime(timezone=True),nullable=False),sa.Column("point_in_time_available_at",sa.DateTime(timezone=True),nullable=False),sa.Column("symbol",sa.String(32),nullable=False),sa.Column("source",sa.String(64),nullable=False),sa.Column("raw_event_id",sa.BigInteger())]
def _hypertable(schema,name):
    op.execute(f"SELECT create_hypertable('{schema}.{name}', 'event_time', if_not_exists => TRUE)")
def upgrade():
    for schema in ("market","derivatives"): op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.create_table("trades",*_base_table("trades"),sa.Column("exchange_trade_id",sa.String(128)),sa.Column("price",sa.Numeric(38,18),nullable=False),sa.Column("size",sa.Numeric(38,18),nullable=False),sa.Column("side",sa.String(16),nullable=False),schema="market")
    op.create_table("orderbook_updates",*_base_table("orderbook_updates"),sa.Column("update_id",sa.BigInteger(),nullable=False),sa.Column("sequence",sa.BigInteger()),sa.Column("side",sa.String(8),nullable=False),sa.Column("price",sa.Numeric(38,18),nullable=False),sa.Column("size",sa.Numeric(38,18),nullable=False),sa.Column("action",sa.String(16),nullable=False),schema="market")
    op.create_table("orderbook_snapshots",*_base_table("orderbook_snapshots"),sa.Column("update_id",sa.BigInteger(),nullable=False),sa.Column("sequence",sa.BigInteger()),sa.Column("bids",postgresql.JSONB(),nullable=False),sa.Column("asks",postgresql.JSONB(),nullable=False),sa.Column("valid",sa.Boolean(),nullable=False),schema="market")
    op.create_table("market_snapshots",*_base_table("market_snapshots"),sa.Column("last_price",sa.Numeric(38,18),nullable=False),sa.Column("bid",sa.Numeric(38,18)),sa.Column("ask",sa.Numeric(38,18)),sa.Column("mid_price",sa.Numeric(38,18)),sa.Column("spread",sa.Numeric(38,18)),sa.Column("volume_24h",sa.Numeric(38,18)),sa.Column("open_interest",sa.Numeric(38,18)),sa.Column("funding_rate",sa.Numeric(38,18)),sa.Column("orderbook_valid",sa.Boolean()),schema="market")
    op.create_table("candles",sa.Column("symbol",sa.String(32),primary_key=True),sa.Column("interval",sa.String(16),primary_key=True),sa.Column("event_time",sa.DateTime(timezone=True),primary_key=True),sa.Column("ingestion_time",sa.DateTime(timezone=True),nullable=False),sa.Column("point_in_time_available_at",sa.DateTime(timezone=True),nullable=False),sa.Column("open",sa.Numeric(38,18),nullable=False),sa.Column("high",sa.Numeric(38,18),nullable=False),sa.Column("low",sa.Numeric(38,18),nullable=False),sa.Column("close",sa.Numeric(38,18),nullable=False),sa.Column("volume",sa.Numeric(38,18),nullable=False),sa.Column("turnover",sa.Numeric(38,18)),sa.Column("source",sa.String(64),nullable=False),sa.Column("raw_event_id",sa.BigInteger()),schema="market")
    for name in ("funding_rates","open_interest","liquidations"):
        cols=_base_table(name)
        if name=="funding_rates": cols += [sa.Column("funding_rate",sa.Numeric(38,18),nullable=False),sa.Column("funding_time",sa.DateTime(timezone=True))]
        elif name=="open_interest": cols += [sa.Column("open_interest",sa.Numeric(38,18),nullable=False)]
        else: cols += [sa.Column("side",sa.String(16),nullable=False),sa.Column("price",sa.Numeric(38,18),nullable=False),sa.Column("size",sa.Numeric(38,18),nullable=False)]
        op.create_table(name,*cols,schema="derivatives")
    for schema,name in [("market","trades"),("market","orderbook_updates"),("market","orderbook_snapshots"),("market","market_snapshots"),("market","candles"),("derivatives","funding_rates"),("derivatives","open_interest"),("derivatives","liquidations")]:
        _hypertable(schema,name)
    for schema,name in [("market","trades"),("market","orderbook_updates"),("market","orderbook_snapshots"),("market","market_snapshots"),("market","candles"),("derivatives","funding_rates"),("derivatives","open_interest"),("derivatives","liquidations")]:
        op.create_index(f"ix_{schema}_{name}_symbol_event_time",name,["symbol","event_time"],schema=schema)
    for table in ("trades","orderbook_updates","orderbook_snapshots","market_snapshots"):
        op.create_index(f"ix_market_{table}_raw_event_id",table,["raw_event_id"],schema="market")

def downgrade():
    for schema,name in [("derivatives","liquidations"),("derivatives","open_interest"),("derivatives","funding_rates"),("market","candles"),("market","market_snapshots"),("market","orderbook_snapshots"),("market","orderbook_updates"),("market","trades")]:
        op.drop_table(name,schema=schema)
