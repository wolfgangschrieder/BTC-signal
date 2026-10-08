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
candles opening strictly after the decision, up to the configured horizon. For new signals, an entry candle touching an exit is ambiguous because OHLC
cannot establish ordering. Historical signals retain their legacy entry-only policy.
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
Statistics reports still use their separate scheduled delivery path. Research outcomes
are resolved independently every 60 seconds, including when Telegram is disabled.
Use `bash deploy/status.sh` on the VPS to inspect data/state lag and outcome counts.

### Audit correctness changes

Live history retains seven days of minute candles (configurable with
`LIVE_HISTORY_MINUTES`, minimum six days). Daily return features can warm up;
reconnects still clear discontinuous history, and no REST candle backfill is implemented.
Order-flow windows exclude trades older than 60 seconds or after the decision.
CVD divergence compares consecutive candle decisions, not the last individual trade.
Weak opposite evidence (at most 25% of the dominant score) remains visible without
forcing abstention; this ratio is a research heuristic requiring validation.

Cooldown is per symbol/direction regardless of entry/SL/TP movement and restores
from committed signal outcomes before the live stream starts. This coordinates
restart recovery for one runtime; it is not a distributed signal-emitter lock.

The current probability engine remains uncalibrated. Development/shadow messages
label it as a research score and EV as hypothetical. `ENVIRONMENT=production`
blocks heuristic signals. Frozen models can be selected explicitly after OOS acceptance
as described below. No market-model acceptance has been inferred from synthetic tests.
Cross-market/news components remain research-only, outside the live directional vote.

Run `alembic upgrade head` before updating the runtime. Migration 0014 persists
per-signal fee/slippage assumptions and an execution policy. Existing signals keep
zero costs and the legacy entry-only policy; resolved historical rows are not rewritten.
New live signals and default replay mark entry-candle exit touches as ambiguous.
Replay can explicitly use `conservative_entry=False` to reproduce the legacy policy.
The fill model uses a limit at the entry-zone midpoint. It does not model fills
anywhere in the zone, order queues, funding, or actual market-order gap prices.
`EXECUTION_FEE_BPS` and `EXECUTION_SLIPPAGE_BPS` are per-side assumptions, default
zero for compatibility; set them explicitly for meaningful net results. EV subtracts
an approximate round-trip cost in risk units but still assumes binary TP1/SL resolution.
Calibration and win rate based on WIN/LOSS are conditional on resolution; EXPIRED
and AMBIGUOUS outcomes are excluded and must not be presented as unconditional success.
The six-hour VPS raw retention policy is unchanged; full historical tick replay
requires separate archival storage.

### Frozen TP1 calibration lifecycle

Migration 0015 adds forecast provenance (`research_score`, model ID, context hash)
and `intelligence.calibration_models`. Historical rows are left NULL and are excluded
from fitting; they are not silently assigned the current model/context. Calibration
uses new, resolved heuristic shadow forecasts under the conservative execution policy.
Forecasts from already-calibrated models are excluded from this initial fitting path.
The context hashes versions, symbol/interval, history, evidence/risk policy, costs,
thresholds, cooldown and market-quality guards. Changing them invalidates a selected model.

`research-os calibration-fit --symbol BTCUSDT --direction long` (or `short`) reads
eligible outcomes, splits chronologically 60/20/20 and purges decisions crossing the
previous partition's latest label availability. Temperature is fitted on TRAIN and
selected on VALIDATION; TEST never tunes it. Default gates require at least 200/100/100
samples after purge, both classes in each partition, ECE <= .05, MCE <= .15, Brier <= .25,
no degradation against raw scores, and improvement over a frozen training-prior baseline.
The actionable test subset above the configured emission threshold also needs at least
30 samples, both classes and calibration error <= .05. Insufficient data returns exit
code 2 without publishing a model. Evaluated artifacts, including rejected reports, are
stored by content hash; rejection never activates a model automatically.

The new target is **confirmed TP1 within the stored horizon**, under the stored simulator.
WIN=1; LOSS, EXPIRED and AMBIGUOUS=0. This is a conservative confirmed-success target,
not actual exchange execution probability or guaranteed net profit. The older
`research-os calibration` command still reports conditional WIN/LOSS diagnostics and
is not a production acceptance gate. EV remains a payoff proxy; complete profitability,
funding/gap validation and operational launch gates are separate requirements.

Explicitly set `CALIBRATION_MODEL_IDS=<long-model-hash>,<short-model-hash>` to load frozen
accepted artifacts. One direction may be selected; unsupported directions abstain.
Models are checked for content hash, acceptance, symbol/context and age (default 30 days
from the latest test-label availability). Missing/rejected/mismatched models stop startup.
A loaded model expires during runtime and abstains outside its fitted raw-score range;
there is no fallback to heuristic production signals or automatic retraining/activation.
Model ID, raw score and context are retained with every emitted forecast for later audit.

No real forecast database was available during development of this feature; tests use
synthetic fixtures. The implementation provides the lifecycle, not a fitted market model.
Run `alembic upgrade head` before starting this runtime. Continue shadow collection until
both directions have enough eligible evidence; do not lower acceptance gates to force launch.
