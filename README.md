# BTC Signal — Research OS

Research-first BTCUSDT signal platform. The system analyzes market data and produces human-readable signals; it never executes trades.

## Principles
- Data quality and point-in-time correctness before signal quality.
- Reproducible state, features, analysis and research.
- No lookahead in replay/backtesting.
- Probability is calibrated, not invented.
- External information is evidence, not an automatic directional vote.
- AI is a research assistant, never the source of truth.
- Bybit is data-only: no order creation, cancellation, amendment, leverage or position management.

## Architecture
`BYBIT → RAW → NORMALIZED → DATA QUALITY → FEATURES → FACTORS → MARKET STATE VECTOR → ANALYSIS → PROBABILITY → SIGNAL → HUMAN → OUTCOME → RESEARCH MEMORY → META-RESEARCH`

## Current stage
Stage 21: external event evidence foundation. Stages are vertical engineering slices; production launch is gated separately by validation and operational acceptance.

## Production roadmap
1. Stage 20 — cross-market / macro data foundation
2. Stage 21 — external event/news evidence (PIT-safe foundation implemented)
3. Stage 22 — research dataset builder + PIT-safe outcome integration
4. Stage 23 — calibration and model validation
5. Stage 24 — signal/risk validation and paper-trading shadow mode
6. Stage 25 — observability, security, recovery and deployment hardening
7. Stage 26 — controlled shadow launch
8. Stage 27 — production signal launch

A production launch is allowed only after all gates pass: deterministic replay, PIT audit, data-quality audit, calibration audit, out-of-sample evaluation, signal/risk acceptance tests, failure/recovery tests, and a successful shadow period. No automatic trading is part of the launch scope.

## Development
Requirements: Python 3.12+, Docker Desktop.

```powershell
copy .env.example .env
docker compose up -d
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m research_os.cli health
```
