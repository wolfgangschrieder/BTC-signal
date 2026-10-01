from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.research import CrossMarketResearchEngine, CrossMarketResearchSnapshot
from research_os.research.cross_market_outcomes import CrossMarketOutcome, compute_btc_outcome

@dataclass(frozen=True)
class CrossMarketDatasetRow:
    timestamp: datetime
    asset: str
    value: float | None
    zscore: float | None
    percentile: float | None
    normalized_available: bool
    sample_size: int
    btc_return_pct: float | None
    btc_mfe_pct: float | None
    btc_mae_pct: float | None

@dataclass(frozen=True)
class CrossMarketDataset:
    symbol: str
    version: str
    rows: tuple[CrossMarketDatasetRow,...]
    skipped: int

class CrossMarketDatasetBuilder:
    """Builds a chronological, PIT-safe research dataset. It never interpolates external data."""
    def __init__(self,research_engine=None):
        self.engine=research_engine or CrossMarketResearchEngine()

    def build(self,symbol,decision_times,observations,candles,horizons=(15,60,240),min_samples=20,window_size=252):
        rows=[]; skipped=0
        ordered=sorted(decision_times)
        for timestamp in ordered:
            snapshot=self.engine.build(timestamp,observations,as_of=timestamp,min_samples=min_samples,window_size=window_size)
            entry=self._entry_price(timestamp,candles)
            if entry is None:
                skipped+=1; continue
            for asset,norm in snapshot.normalized.items():
                for horizon in horizons:
                    outcome=compute_btc_outcome(timestamp,asset,norm.zscore,candles,horizon,entry)
                    if outcome is None:
                        skipped+=1
                        continue
                    rows.append(CrossMarketDatasetRow(
                        timestamp,asset,norm.value,norm.zscore,norm.percentile,
                        norm.available,norm.sample_size,outcome.btc_return_pct,
                        outcome.btc_mfe_pct,outcome.btc_mae_pct))
        return CrossMarketDataset(symbol,f"cross-market-dataset-v2:{min_samples}:{window_size}:{','.join(map(str,horizons))}",tuple(rows),skipped)

    @staticmethod
    def _entry_price(timestamp,candles):
        candidates=[c for c in candles if c.timestamp==timestamp]
        return None if not candidates else float(candidates[-1].close)

    @staticmethod
    def chronological_split(dataset,train_ratio=.7):
        if not .5 <= train_ratio < 1:
            raise ValueError("train_ratio must be in [0.5, 1)")
        ordered=sorted(dataset.rows,key=lambda x:x.timestamp)
        cut=int(len(ordered)*train_ratio)
        return tuple(ordered[:cut]),tuple(ordered[cut:])
