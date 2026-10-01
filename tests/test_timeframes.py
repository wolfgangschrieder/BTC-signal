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
