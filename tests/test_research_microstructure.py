from datetime import datetime, timezone
from research_os.research.microstructure import OFIObservation, aggregate_cross_exchange
from research_os.research.lead_lag import scan_lead_lag

def test_multi_exchange_ofi_normalizes_before_aggregation():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    obs=(
        OFIObservation("binance",t,10.0,tuple(float(x) for x in range(1,31))),
        OFIObservation("bybit",t,20.0,tuple(float(x*2) for x in range(1,31))),
    )
    result=aggregate_cross_exchange(t,obs,min_samples=20,window_size=30)
    assert result.available
    assert len(result.components)==2
    assert result.aggregate is not None
    assert result.components[0].zscore is not None
    assert result.components[1].zscore is not None

def test_multi_exchange_ofi_stays_unavailable_without_baseline():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    result=aggregate_cross_exchange(t,(OFIObservation("coinbase",t,1.0,(1.0,2.0)),),min_samples=20)
    assert not result.available
    assert result.aggregate is None

def test_lead_lag_scans_requested_lags_without_declaring_trading_rule():
    a=[float(i) for i in range(100)]
    b=[0.0]*5+a[:-5]
    results=scan_lead_lag("binance","bybit",a,b,lags=(1,5,15),min_samples=30)
    assert [r.lag_seconds for r in results]==[1,5,15]
    assert all(r.sample_size > 0 for r in results)
    assert any(r.stable for r in results)


def test_raw_ofi_is_computed_from_top_levels_only():
    from decimal import Decimal
    from research_os.exchanges.bybit.orderbook import OrderBookLevel, OrderBookState
    from research_os.research.microstructure import compute_order_flow_imbalance
    def book(bids,asks,uid):
        return OrderBookState("BTCUSDT",
            tuple(OrderBookLevel(Decimal(str(p)),Decimal(str(s))) for p,s in bids),
            tuple(OrderBookLevel(Decimal(str(p)),Decimal(str(s))) for p,s in asks),
            uid,None,True,uid,"valid")
    previous=book([(100,5),(99,4),(98,3),(97,2),(96,1),(95,100)],
                  [(101,5),(102,4),(103,3),(104,2),(105,1),(106,100)],1)
    current=book([(100,7),(99,4),(98,3),(97,2),(96,1),(95,1)],
                 [(101,3),(102,4),(103,3),(104,2),(105,1),(106,1)],2)
    assert compute_order_flow_imbalance(previous,current,levels=5)==4.0

def test_raw_ofi_rejects_invalid_books():
    from research_os.research.microstructure import compute_order_flow_imbalance
    assert compute_order_flow_imbalance(None,None) is None
