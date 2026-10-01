from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from research_os.intelligence.probability import CalibrationMetrics,CalibrationSample

@dataclass(frozen=True)
class CalibrationBucket:
    lower: float
    upper: float
    samples: int
    predicted_mean: float
    actual_rate: float
    calibration_error: float

@dataclass(frozen=True)
class CalibrationReport:
    samples: int
    brier: float
    log_loss: float
    buckets: tuple[CalibrationBucket,...]
    max_calibration_error: float
    expected_calibration_error: float

class CalibrationLab:
    """Measures probability quality without changing the model or thresholds."""
    def __init__(self,bucket_count:int=10):
        if bucket_count<2: raise ValueError("bucket_count must be >= 2")
        self.bucket_count=bucket_count

    def evaluate(self,samples:list[CalibrationSample])->CalibrationReport:
        if not samples:
            return CalibrationReport(0,0.0,0.0,(),0.0,0.0)
        groups=defaultdict(list)
        for s in samples:
            p=min(1.0,max(0.0,s.predicted))
            idx=min(self.bucket_count-1,int(p*self.bucket_count))
            groups[idx].append((p,s.outcome))
        buckets=[]
        for idx in range(self.bucket_count):
            rows=groups.get(idx,[])
            lower=idx/self.bucket_count; upper=(idx+1)/self.bucket_count
            if not rows:
                buckets.append(CalibrationBucket(lower,upper,0,0.0,0.0,0.0)); continue
            pm=sum(p for p,_ in rows)/len(rows); actual=sum(y for _,y in rows)/len(rows)
            buckets.append(CalibrationBucket(lower,upper,len(rows),pm,actual,abs(pm-actual)))
        nonempty=[b for b in buckets if b.samples]
        ece=sum(b.samples* b.calibration_error for b in nonempty)/len(samples)
        mce=max((b.calibration_error for b in nonempty),default=0.0)
        return CalibrationReport(len(samples),CalibrationMetrics.brier(samples),CalibrationMetrics.log_loss(samples),tuple(buckets),mce,ece)

    @staticmethod
    def from_outcomes(rows):
        return [CalibrationSample(float(r["probability"]),1 if r["status"]=="win" else 0) for r in rows if r["status"] in ("win","loss")]
