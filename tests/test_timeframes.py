from datetime import datetime,timedelta,timezone
from research_os.features.timeframes import OHLCVBar,Timeframe,aggregate_bars,MultiTimeframeFeatureEngine,analyze_alignment

def bars(n=10):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    return [OHLCVBar(start+timedelta(minutes=i),100+i,101+i,99+i,100+i,1.0) for i in range(n)]

def test_aggregate_5m_requires_complete_contiguous_input():
    result=aggregate_bars(bars(10),Timeframe.M5)
    assert len(result)==2
    assert result[0].open==100 and result[0].close==104
    assert result[0].high==105 and result[0].low==99
    assert result[0].volume==5

def test_aggregate_does_not_fill_gaps():
    source=bars(10)
    source.pop(4)
    result=aggregate_bars(source,Timeframe.M5)
    assert len(result)==1
    assert result[0].timestamp.minute==5

def test_multitimeframe_is_deterministic_and_marks_missing_timeframes_unavailable():
    snapshot=MultiTimeframeFeatureEngine().build("BTCUSDT",bars(20),datetime(2026,1,1,0,20,tzinfo=timezone.utc))
    assert snapshot==MultiTimeframeFeatureEngine().build("BTCUSDT",bars(20),datetime(2026,1,1,0,20,tzinfo=timezone.utc))
    assert snapshot.snapshots[Timeframe.M1].features
    assert snapshot.snapshots[Timeframe.H1].features[0].available is False

def test_alignment_exposes_conflict_without_probability():
    snapshot=MultiTimeframeFeatureEngine().build("BTCUSDT",bars(20),datetime(2026,1,1,0,20,tzinfo=timezone.utc))
    alignment=analyze_alignment(snapshot)
    assert alignment.direction=="bullish"
    assert not alignment.conflicting
    assert alignment.version=="mtf-alignment-v1"

def test_point_in_time_excludes_unavailable_current_bar():
    source=bars(6)
    decision=datetime(2026,1,1,0,5,tzinfo=timezone.utc)
    snapshot=MultiTimeframeFeatureEngine().build("BTCUSDT",source,decision,as_of=decision)
    one_min=snapshot.snapshots[Timeframe.M1]
    returns={x.name:x for x in one_min.features}
    assert returns["return_1"].available is True
    assert returns["return_1"].value == (104/103)-1

def test_unified_msv_namespaces_each_timeframe():
    from research_os.market.state_builder import MarketStateBuilder
    source=bars(20)
    decision=datetime(2026,1,1,0,20,tzinfo=timezone.utc)
    snapshot=MultiTimeframeFeatureEngine().build("BTCUSDT",source,decision,as_of=decision)
    state=MarketStateBuilder().build_multi("BTCUSDT",decision,decision,decision,snapshot)
    assert "tf_1m_return_1" in state.values
    assert "tf_5m_return_1" in state.values
    assert state.availability["tf_1h_return_1"] is False

def test_mtf_state_is_attached_and_persisted_in_msv():
    from research_os.market.state_builder import MarketStateBuilder
    source=bars(1500)
    decision=datetime(2026,1,2,tzinfo=timezone.utc)
    snapshot=MultiTimeframeFeatureEngine().build("BTCUSDT",source,decision,as_of=decision)
    assert snapshot.state is not None
    assert snapshot.state.version=="mtf-state-v1"
    state=MarketStateBuilder().build_multi("BTCUSDT",decision,decision,decision,snapshot)
    assert state.values["mtf_alignment"] in {"bullish","bearish","conflicting","neutral"}
    assert state.availability["mtf_strength"] is True
