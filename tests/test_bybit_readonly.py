import json
import httpx
import pytest
from research_os.execution.bybit_readonly import BybitReadonlyAdapter, BybitReadonlyConfig
from research_os.execution.service import ExecutionStatus

def test_readonly_adapter_maps_order_state_and_signs_request():
    seen={}
    def handler(request):
        seen["path"]=request.url.path
        seen["query"]=str(request.url.query)
        seen["api_key"]=request.headers["X-BAPI-API-KEY"]
        seen["signature"]=request.headers["X-BAPI-SIGN"]
        return httpx.Response(200,json={"retCode":0,"retMsg":"OK","result":{"list":[{
            "orderLinkId":"rs-abc","orderId":"ex-1","orderStatus":"PartiallyFilled",
            "rejectReason":"EC_NoError","cancelType":"UNKNOWN"}]}})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    adapter=BybitReadonlyAdapter(BybitReadonlyConfig("key","secret"),client)
    state=adapter.get_order("rs-abc")
    assert state is not None
    assert state.status is ExecutionStatus.PARTIALLY_FILLED
    assert state.exchange_order_id=="ex-1"
    assert seen["path"]=="/v5/order/realtime"
    assert "orderLinkId=rs-abc" in seen["query"]
    assert seen["api_key"]=="key"
    assert len(seen["signature"])==64

def test_readonly_adapter_refuses_submit():
    adapter=BybitReadonlyAdapter(BybitReadonlyConfig("key","secret"),httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(RuntimeError,match="cannot submit"):
        adapter.submit(None)

def test_readonly_adapter_returns_none_for_missing_order():
    client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200,json={"retCode":0,"retMsg":"OK","result":{"list":[]}})))
    adapter=BybitReadonlyAdapter(BybitReadonlyConfig("key","secret"),client)
    assert adapter.get_order("missing") is None
