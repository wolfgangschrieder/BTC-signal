from research_os.pipeline.latency import LatencyHistogram, LatencyTelemetry

def test_latency_percentiles():
    h=LatencyHistogram()
    for x in range(1,101): h.observe(float(x))
    assert h.percentile(.50)==50
    assert h.percentile(.99)==99

def test_latency_timer_and_report():
    t=LatencyTelemetry()
    with t.timer("ws_normalization"):
        pass
    report=t.report()
    assert report["ws_normalization"]["count"]==1
    assert report["ws_normalization"]["min_ms"] is not None
    assert report["ws_normalization"]["p99_ms"] is not None
    assert report["ws_normalization"]["max_ms"] is not None
