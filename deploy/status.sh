#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
compose=(docker compose --env-file deploy/.env -f deploy/compose.yml)
df -h .
"${compose[@]}" ps -a
"${compose[@]}" exec -T postgres df -h /var/lib/postgresql/data
"${compose[@]}" exec -T app research-os health || true
"${compose[@]}" exec -T postgres psql -U research_os -d research_os -c "
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;
SELECT pg_size_pretty(coalesce(sum(size),0)::bigint) AS wal_size FROM pg_ls_waldir();
SELECT event_type, count(*) AS events, max(ingestion_time) AS latest_received,
       now()-max(ingestion_time) AS lag
FROM raw.events WHERE source='bybit' GROUP BY event_type ORDER BY event_type;
SELECT count(*) AS states, max(decision_time) AS latest_decision,
       now()-max(decision_time) AS lag FROM world.market_state_vectors;
SELECT status, count(*) AS outcomes FROM signal_outcomes GROUP BY status ORDER BY status;
SELECT count(*) AS queued_notifications FROM notification_outbox WHERE sent_at IS NULL;
"
