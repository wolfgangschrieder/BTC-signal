from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class CrossMarketTransform:
    asset: str
    raw_feature: str
    transformed_feature: str
    method: str

DEFAULT_TRANSFORMS={
    "DOLLAR_BROAD": CrossMarketTransform("DOLLAR_BROAD","level","return","relative_change"),
    "SPX": CrossMarketTransform("SPX","level","return","relative_change"),
    "NASDAQ": CrossMarketTransform("NASDAQ","level","return","relative_change"),
    "VIX": CrossMarketTransform("VIX","level","change","absolute_change"),
    "US10Y": CrossMarketTransform("US10Y","level","change_bps","basis_points_change"),
}

def transform(current,previous,asset):
    if previous is None:
        return None
    if asset=="US10Y":
        return (float(current)-float(previous))*100.0
    if asset=="VIX":
        return float(current)-float(previous)
    if previous==0:
        return None
    return (float(current)-float(previous))/abs(float(previous))

def transform_metadata(asset):
    return DEFAULT_TRANSFORMS.get(asset)
