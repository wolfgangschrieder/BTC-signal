"""Read-only scoring diagnostics; does not estimate strategy profitability."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from statistics import quantiles

from sqlalchemy import text

from research_os.database.session import SessionLocal
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import EvidenceDirection
from research_os.intelligence.probability import ProbabilityEngine
from research_os.market.state_vector import MarketStateVector


def summarize(rows, threshold=0.70):
    analyzer, probability = MarketAnalyzer(), ProbabilityEngine()
    directions, reasons, features = Counter(), Counter(), Counter()
    scores = []
    candidates = 0
    first = last = None
    for row in rows:
        vector = row['vector']
        state = MarketStateVector.build(
            row['symbol'], row['timestamp'], row['decision_time'],
            row['point_in_time_available_at'], vector['values'], vector['availability'],
            row['data_quality'], row['feature_version'], row['vector_version'],
        )
        analysis = analyzer.analyze(state)
        predicted = probability.predict(analysis)
        directions[analysis.direction.value] += 1
        reasons[analysis.reason] += 1
        features.update(key for key, available in state.availability.items() if available)
        score = max(predicted.long, predicted.short)
        scores.append(score)
        if (analysis.direction is EvidenceDirection.BULLISH and predicted.long >= threshold
                or analysis.direction is EvidenceDirection.BEARISH and predicted.short >= threshold):
            candidates += 1
        first = min(first, state.decision_time) if first else state.decision_time
        last = max(last, state.decision_time) if last else state.decision_time
    q = quantiles(scores, n=100, method='inclusive') if len(scores) > 1 else None
    return {
        'scope': 'Current model rescoring of saved states; not historical execution replay or calibration',
        'model_version': probability.version,
        'states': len(scores),
        'first_decision': first.isoformat() if first else None,
        'last_decision': last.isoformat() if last else None,
        'analysis_directions': dict(directions),
        'analysis_reasons': dict(reasons),
        'directional_score': {
            'median': q[49] if q else (scores[0] if scores else None),
            'p90': q[89] if q else (scores[0] if scores else None),
            'max': max(scores) if scores else None,
        },
        'threshold': threshold,
        'direction_candidates_above_threshold': candidates,
        'available_feature_counts': dict(sorted(features.items())),
        'limitations': 'Candidates still require ATR, risk levels, live execution guard and persistence. Scores are uncalibrated; no returns or success rates are measured.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', default='BTCUSDT')
    parser.add_argument('--limit', type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100000:
        parser.error('--limit must be between 1 and 100000')
    with SessionLocal() as session:
        rows = session.execute(text('''
            SELECT symbol,timestamp,decision_time,point_in_time_available_at,
                   vector_version,feature_version,vector,data_quality
            FROM world.market_state_vectors WHERE symbol=:symbol
            ORDER BY decision_time DESC LIMIT :limit
        '''), {'symbol': args.symbol, 'limit': args.limit}).mappings()
        report = summarize(rows)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
