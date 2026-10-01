from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from research_os.signals.outcomes import SignalOutcome, OutcomeStatus

@dataclass(frozen=True)
class SignalStatistics:
    sample_size: int
    wins: int
    losses: int
    expired: int
    win_rate: float
    mean_return: float | None
    mean_mfe: float | None
    mean_mae: float | None

def summarize(outcomes: list[SignalOutcome] | tuple[SignalOutcome,...]) -> SignalStatistics:
    """Evaluate every generated signal outcome, regardless of human interaction."""
    n=len(outcomes)
    counts=Counter(x.status for x in outcomes)
    returns=[x.realized_return for x in outcomes if x.realized_return is not None]
    mfes=[x.mfe for x in outcomes if x.mfe is not None]
    maes=[x.mae for x in outcomes if x.mae is not None]
    resolved=counts[OutcomeStatus.WIN]+counts[OutcomeStatus.LOSS]
    return SignalStatistics(
        sample_size=n,
        wins=counts[OutcomeStatus.WIN],
        losses=counts[OutcomeStatus.LOSS],
        expired=counts[OutcomeStatus.EXPIRED],
        win_rate=counts[OutcomeStatus.WIN]/resolved if resolved else 0.0,
        mean_return=sum(returns)/len(returns) if returns else None,
        mean_mfe=sum(mfes)/len(mfes) if mfes else None,
        mean_mae=sum(maes)/len(maes) if maes else None,
    )
