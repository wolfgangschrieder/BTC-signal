from datetime import datetime, timezone
from research_os.cross_market.transforms import transform, transform_metadata

def test_transform_us10y_uses_basis_points():
    assert transform(4.25,4.10,"US10Y")==15.0

def test_transform_vix_uses_absolute_change():
    assert transform(25,20,"VIX")==5

def test_equity_and_dollar_use_relative_change():
    assert transform(105,100,"SPX")==.05
    assert transform(105,100,"DOLLAR_BROAD")==.05

def test_metadata_declares_semantics():
    assert transform_metadata("US10Y").method=="basis_points_change"
