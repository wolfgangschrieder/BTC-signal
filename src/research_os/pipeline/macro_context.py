"""Bounded, read-only macro context; no network or database calls on the hot path."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from sqlalchemy import text

from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.providers import DEFAULT_FRED_SERIES
from research_os.database.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MacroCache:
    loaded_at: datetime
    observations: tuple[CrossMarketObservation, ...]


class LiveMacroContext:
    version = 'live-macro-context-v1'

    def __init__(self, refresh_seconds=60, cache_max_age_seconds=120, max_event_age_days=7):
        if min(refresh_seconds, cache_max_age_seconds, max_event_age_days) <= 0:
            raise ValueError('Macro context intervals must be positive')
        self.refresh_seconds = refresh_seconds
        self.cache_max_age_seconds = cache_max_age_seconds
        self.max_event_age_days = max_event_age_days
        self.cache: MacroCache | None = None

    def refresh(self):
        cutoff = datetime.now(UTC)
        observations = []
        try:
            with SessionLocal() as session:
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                for asset, series in DEFAULT_FRED_SERIES.items():
                    # One immutable latest-known vintage per date, two distinct dates,
                    # and one pinned source. Never mix sources or same-day revisions.
                    rows = session.execute(text('''
                        SELECT DISTINCT ON (event_time)
                            event_time, point_in_time_available_at, value, unit
                        FROM intelligence.cross_market_observations
                        WHERE asset=:asset AND source=:source
                          AND event_time BETWEEN :lower AND :cutoff
                          AND point_in_time_available_at<=:cutoff
                        ORDER BY event_time DESC, point_in_time_available_at DESC, id DESC
                        LIMIT 2
                    '''), {'asset': asset, 'source': f'fred:{series}', 'cutoff': cutoff,
                           'lower': cutoff - timedelta(days=14)}).mappings().all()
                    for row in rows:
                        observations.append(CrossMarketObservation(
                            asset, row['event_time'], row['point_in_time_available_at'],
                            float(row['value']), f'fred:{series}', row['unit']))
            self.cache = MacroCache(datetime.now(UTC), tuple(observations))
        except Exception:
            self.cache = None
            raise

    def features(self, timestamp: datetime, decision_time: datetime):
        values = {f'cross_market_{asset}_return': None for asset in DEFAULT_FRED_SERIES}
        availability = dict.fromkeys(values, False)
        quality = {'cross_market_status': 'unavailable', 'cross_market_version': self.version}
        cache = self.cache
        if cache is None:
            return values, availability, quality
        age = (decision_time - cache.loaded_at).total_seconds()
        if age < 0 or age > self.cache_max_age_seconds:
            quality['cross_market_status'] = 'stale_cache'
            return values, availability, quality
        provenance = {}
        for asset in DEFAULT_FRED_SERIES:
            history = sorted((o for o in cache.observations if o.asset == asset
                              and o.timestamp <= timestamp
                              and o.point_in_time_available_at <= decision_time),
                             key=lambda o: o.timestamp, reverse=True)
            if len(history) != 2:
                continue
            current, previous = history
            if (timestamp - current.timestamp).total_seconds() > self.max_event_age_days * 86400:
                continue
            if previous.timestamp >= current.timestamp or previous.value == 0:
                continue
            change = (current.value - previous.value) / abs(previous.value)
            if not isfinite(change):
                continue
            name = f'cross_market_{asset}_return'
            values[name] = change
            availability[name] = True
            provenance[asset] = {
                'source': current.source, 'unit': current.unit,
                'current_time': current.timestamp.isoformat(),
                'previous_time': previous.timestamp.isoformat(),
                'current_pit': current.point_in_time_available_at.isoformat(),
                'previous_pit': previous.point_in_time_available_at.isoformat(),
                'current_value': current.value, 'previous_value': previous.value,
            }
        quality['cross_market_status'] = 'available' if provenance else 'no_fresh_pairs'
        quality['cross_market_provenance'] = json.dumps(provenance, sort_keys=True)
        quality['cross_market_cache_loaded_at'] = cache.loaded_at.isoformat()
        return values, availability, quality

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            try:
                await asyncio.to_thread(self.refresh)
            except Exception as error:  # noqa: BLE001 - optional context retries cold-path failures
                logger.warning('Macro context unavailable (%s)', type(error).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.refresh_seconds)
            except TimeoutError:
                pass
