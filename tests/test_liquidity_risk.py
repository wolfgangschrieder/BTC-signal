from research_os.features.liquidity import LiquidityCluster
from research_os.signals.risk import RiskEngine, RiskPolicy

def test_nonpersistent_cluster_falls_back_to_atr():
    cluster=LiquidityCluster("bid",97.9,98.1,98.0,500.0,4,0.99,200.0,False)
    levels=RiskEngine().build_levels("long",100,2,(),(cluster,))
    assert levels.stop_source=="atr"

def test_persistent_cluster_drives_dynamic_stop():
    cluster=LiquidityCluster("bid",97.9,98.1,98.0,500.0,4,0.99,200.0,True,1000,3000,2000)
    levels=RiskEngine().build_levels("long",100,2,(),(cluster,))
    assert levels.stop_source=="liquidity"
    assert levels.stop_loss < 98
