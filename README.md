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

### Signal time and candle evaluation

Market-state `timestamp` is the source candle open time; `decision_time` is when
the state is evaluated. Analysis, probability and signals use `decision_time`,
while evidence retains the source timestamp. Live outcomes and replay only use
candles opening strictly after the decision, up to the configured horizon. The
entry candle only fills the entry; TP/SL are evaluated on subsequent candles.
Replay fixtures with delayed data must supply `point_in_time_available_at`.
Existing historical signal timestamps are not rewritten by this change.

### Durable signal notifications

Run `alembic upgrade head` before starting the live runtime. Migration
`0012_notification_outbox` stores each signal's Telegram message and chat ID in
the same transaction as its pending outcome. The delivery worker sends committed
messages, records attempts and delivery status, and retries failures with bounded
exponential backoff. Database operations run in worker threads; no transaction
remains open during the HTTP request. A 60-second lease and claim token coordinate
multiple workers and allow recovery after a crash. Only messages for the configured
chat ID are claimed. Bot tokens and HTTP error details are not stored in the outbox.

Delivery is at least once: a crash after Telegram accepts a message but before the
database records success can cause a duplicate. The signal ID identifies the
notification; Telegram sendMessage does not provide an idempotency key. Pending
committed messages survive runtime restarts. Signals that fail the initial database
transaction are not sent, and new signal emission is blocked by persistence health.
Statistics reports still use their separate scheduled delivery path.
