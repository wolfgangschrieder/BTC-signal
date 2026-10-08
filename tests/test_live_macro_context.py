import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.repository import CrossMarketRepository
from research_os.database.session import SessionLocal
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import EvidenceDirection
from research_os.intelligence.probability import ProbabilityEngine
from research_os.pipeline.live import LiveSignalService
from research_os.pipeline.macro_context import LiveMacroContext, MacroCache

NOW = datetime(2026, 10, 9, tzinfo=UTC)


def observation(days, value, pit=None):
    return CrossMarketObservation('SPX', NOW - timedelta(days=days), pit or max(NOW, NOW - timedelta(days=days)),
                                  value, 'fred:SP500')


def context(*observations):
    result = LiveMacroContext()
    result.cache = MacroCache(NOW, observations)
    return result


def test_macro_pair_is_bounded_and_reproducible():
    values, available, quality = context(observation(1, 110), observation(2, 100)).features(NOW, NOW)
    assert len(values) == 5
    assert values['cross_market_SPX_return'] == pytest.approx(.1)
    assert available['cross_market_SPX_return']
    assert not available['cross_market_VIX_return']
    provenance = json.loads(quality['cross_market_provenance'])['SPX']
    assert provenance['source'] == 'fred:SP500'
    assert provenance['previous_value'] == 100


@pytest.mark.parametrize('decision', [NOW - timedelta(seconds=1), NOW + timedelta(seconds=121)])
def test_cache_unavailable_before_loading_or_after_expiry(decision):
    values, available, _ = context(observation(1, 110), observation(2, 100)).features(NOW, decision)
    assert not any(available.values())
    assert all(v is None for v in values.values())


@pytest.mark.parametrize('observations', [
    (observation(1, 110, NOW + timedelta(seconds=1)), observation(2, 100)),
    (observation(-1, 110), observation(2, 100)),
    (observation(8, 110), observation(9, 100)),
    (observation(1, 110), observation(2, 0)),
    (observation(1, 110), observation(1, 100)),
])
def test_invalid_pairs_cannot_become_available(observations):
    _, available, _ = context(*observations).features(NOW, NOW)
    assert not any(available.values())


def test_macro_evidence_does_not_change_probability():
    values = {'return_1': .01, 'return_5': .03}
    availability = dict.fromkeys(values, True)
    state = SimpleNamespace(values=values, availability=availability, timestamp=NOW,
                            decision_time=NOW, symbol='BTCUSDT')
    baseline = ProbabilityEngine().predict(MarketAnalyzer().analyze(state))
    values['cross_market_SPX_return'] = .99
    availability['cross_market_SPX_return'] = True
    analysis = MarketAnalyzer().analyze(state)
    assert analysis.evidence[-1].direction is EvidenceDirection.NEUTRAL
    assert ProbabilityEngine().predict(analysis) == baseline


def test_configuration_versions_calibration_context():
    disabled = LiveSignalService()
    enabled = LiveSignalService(settings=SimpleNamespace(cross_market_enabled=True))
    assert enabled.macro_context is not None
    assert disabled.macro_context is None
    assert enabled.calibration_context != disabled.calibration_context


def test_refresh_failure_discards_cache(monkeypatch):
    cache = context(observation(1, 110), observation(2, 100))

    def unavailable():
        raise RuntimeError('offline')

    monkeypatch.setattr('research_os.pipeline.macro_context.SessionLocal', unavailable)
    with pytest.raises(RuntimeError):
        cache.refresh()
    assert cache.cache is None


@pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='requires migrated PostgreSQL')
def test_refresh_selects_latest_known_distinct_dates(monkeypatch):
    now = datetime.now(UTC)
    with SessionLocal() as session:
        try:
            repository = CrossMarketRepository()
            for days, value, pit in [(1, 100, now - timedelta(seconds=4)),
                                     (1, 110, now - timedelta(seconds=2)),
                                     (1, 999, now + timedelta(days=1)),
                                     (2, 90, now - timedelta(seconds=4))]:
                repository.save(session, CrossMarketObservation(
                    'SPX', now - timedelta(days=days), pit, value, 'fred:SP500'))

            @contextmanager
            def same_transaction():
                yield session

            monkeypatch.setattr('research_os.pipeline.macro_context.SessionLocal', same_transaction)
            cache = LiveMacroContext()
            cache.refresh()
            observations = [o for o in cache.cache.observations if o.asset == 'SPX']
            assert len(observations) == 2
            assert [o.value for o in observations] == [110, 90]
            assert len(cache.cache.observations) <= 10
        finally:
            session.rollback()


@pytest.mark.asyncio
async def test_macro_worker_runs_off_thread_and_stops(monkeypatch):
    import asyncio
    from threading import Event
    called = Event()
    cache = LiveMacroContext(refresh_seconds=3600)
    monkeypatch.setattr(cache, 'refresh', called.set)
    stop = asyncio.Event()
    worker = asyncio.create_task(cache.run(stop))
    assert await asyncio.to_thread(called.wait, 1)
    stop.set()
    await asyncio.wait_for(worker, 1)
