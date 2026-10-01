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
Stage 0: foundation. The repository intentionally starts small and grows through tested vertical slices.

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
