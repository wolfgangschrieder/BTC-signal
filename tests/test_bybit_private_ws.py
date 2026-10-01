import json
from research_os.execution.bybit_private_ws import BybitPrivateOrderStream, BybitPrivateWSConfig
from research_os.execution.service import ExecutionStatus

def test_private_ws_auth_signature_shape():
    args=BybitPrivateOrderStream._auth_args("key","secret",123)
    assert args[0]=="key"
    assert args[1]==123
    assert len(args[2])==64

def test_private_ws_parses_order_updates():
    message=json.dumps({"topic":"order","data":[
        {"orderLinkId":"rs-1","orderId":"ex-1","orderStatus":"Filled","rejectReason":"EC_NoError"},
        {"orderLinkId":"rs-2","orderId":"ex-2","orderStatus":"PartiallyFilled","cancelType":"UNKNOWN"},
        {"orderLinkId":"","orderId":"ex-3","orderStatus":"Filled"}]})
    states=BybitPrivateOrderStream.parse_message(message)
    assert [(s.client_order_id,s.status,s.exchange_order_id) for s in states]==[
        ("rs-1",ExecutionStatus.FILLED,"ex-1"),
        ("rs-2",ExecutionStatus.PARTIALLY_FILLED,"ex-2"),
    ]
