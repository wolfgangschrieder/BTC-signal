import pytest
from research_os.cross_market.providers import FREDProvider

class FakeResponse:
    def raise_for_status(self): pass
    def json(self):
        return {"observations":[
            {"date":"2026-01-02","value":"100.5","realtime_start":"2026-01-03","realtime_end":"2026-01-03"},
            {"date":"2026-01-03","value":"."},
        ]}

class FakeClient:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def get(self,*args,**kwargs): return FakeResponse()

@pytest.mark.asyncio
async def test_fred_provider_preserves_acquisition_pit(monkeypatch):
    import research_os.cross_market.providers as module
    monkeypatch.setattr(module.httpx,"AsyncClient",lambda **kwargs: FakeClient())
    result=await FREDProvider("test-key").fetch_series("VIX","VIXCLS")
    assert len(result)==1
    assert result[0].value==100.5
    assert result[0].source=="fred:VIXCLS"
    assert result[0].point_in_time_available_at>=result[0].timestamp
    assert result[0].payload["realtime_start"]=="2026-01-03"

def test_fred_provider_requires_key():
    with pytest.raises(ValueError):
        FREDProvider("")


@pytest.mark.asyncio
async def test_fred_pit_starts_after_decoding_response(monkeypatch):
    from datetime import UTC, datetime
    import research_os.cross_market.providers as module
    received = False

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 9, 0, 1 if received else 0, tzinfo=UTC)

    original_json = FakeResponse.json

    def decoded(self):
        nonlocal received
        received = True
        return original_json(self)

    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(FakeResponse, 'json', decoded)
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: FakeClient())
    result = await FREDProvider('test-key').fetch_series('VIX', 'VIXCLS')
    assert result[0].point_in_time_available_at == datetime(2026, 10, 9, 0, 1, tzinfo=UTC)
