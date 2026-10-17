# Signal evaluation without real trades

Each emitted signal has independent direction and hypothetical execution labels.
No real orders are submitted.

Direction is evaluated at 15/30/60 minutes: signed close-to-reference return,
favorable and adverse excursions. Positive means correct direction; zero is flat.
Gross price returns are not trade P&L or calibrated probabilities. Report each
horizon separately and exclude pending/insufficient labels from accuracy.

Reference is the last closed 1m candle known at decision time, at most 2 minutes
old. Persist price/time/source. This is a minute-price proxy, not an executable
quote at the exact decision. Endpoint is the last full minute ending at/before
the horizon. Excursions exclude partial boundary minutes. Require every full
intervening candle. Retry gaps for 24h, then label insufficient_data. Forecasts
continue after execution resolves. Historical signals receive labels under
these documented rules; existing execution outcomes are not rewritten.

Expired executions additionally record unfilled, filled_expired, or
insufficient_data. Complete filled_expired scenarios store horizon_return at
the final eligible candle close with adverse exit slippage and fees on both
sides. It remains separate from realized_return and TP1 calibration labels.
Unfilled is not zero profit and not a failed direction forecast. Historical
expired rows remain unclassified. Observation reports and auditor evidence
include both tracks. Migration 0021 is required before starting the new app.
