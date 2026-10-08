from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from research_os.pipeline.storage import GB, StorageBudget


def setup_probe(monkeypatch, free=6 * GB, size=17 * GB):
    monkeypatch.setattr('research_os.pipeline.storage.shutil.disk_usage',
                        lambda _: SimpleNamespace(free=free))
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = size
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    monkeypatch.setattr('research_os.pipeline.storage.SessionLocal', factory)


def test_storage_requires_successful_probe(monkeypatch):
    setup_probe(monkeypatch)
    budget = StorageBudget('/pg', 18, 5)
    with pytest.raises(RuntimeError):
        budget.require_writable()
    budget.check()
    budget.require_writable()


@pytest.mark.parametrize('free,size', [(4 * GB, 1 * GB), (6 * GB, 18 * GB)])
def test_limits_block_writes(monkeypatch, free, size):
    setup_probe(monkeypatch, free, size)
    budget = StorageBudget('/pg', 18, 5)
    with pytest.raises(RuntimeError, match='budget exceeded'):
        budget.check()
    with pytest.raises(RuntimeError):
        budget.require_writable()


def test_failed_probe_revokes_previous_authorization(monkeypatch):
    setup_probe(monkeypatch)
    budget = StorageBudget('/pg', 18, 5)
    budget.check()

    def inaccessible(_):
        raise PermissionError('volume inaccessible')

    monkeypatch.setattr('research_os.pipeline.storage.shutil.disk_usage', inaccessible)
    with pytest.raises(PermissionError):
        budget.check()
    with pytest.raises(RuntimeError):
        budget.require_writable()


@pytest.mark.asyncio
async def test_monitor_failure_propagates(monkeypatch):
    import asyncio
    setup_probe(monkeypatch, free=4 * GB)
    budget = StorageBudget('/pg', 18, 5, interval_seconds=.001)
    with pytest.raises(RuntimeError):
        await budget.run(asyncio.Event())


def test_ingestion_blocked_before_opening_transaction(monkeypatch):
    from research_os.data.pipeline import IngestionPipeline
    budget = StorageBudget('/pg', 18, 5)
    factory = MagicMock()
    monkeypatch.setattr('research_os.data.pipeline.SessionLocal', factory)
    pipeline = IngestionPipeline(storage_budget=budget)
    with pytest.raises(RuntimeError, match='ingestion blocked'):
        pipeline._persist_one(None)
    factory.assert_not_called()
