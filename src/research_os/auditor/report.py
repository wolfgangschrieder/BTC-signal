"""Read a complete saved analyst report without calling an external API."""
from sqlalchemy import text

from research_os.auditor.models import AnalystReport, message
from research_os.database.session import SessionLocal


def saved_report(identity=None):
    with SessionLocal() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        row = session.execute(text("""
            SELECT run_id,kind,period_start,period_end,report,snapshot
            FROM intelligence.auditor_runs
            WHERE status='completed' AND (CAST(:id AS uuid) IS NULL OR run_id=CAST(:id AS uuid))
            ORDER BY created_at DESC LIMIT 1
        """), {'id': identity}).mappings().first()
    if row is None:
        print('Завершённый отчёт не найден.')
        return 1
    report = AnalystReport.model_validate(row['report'])
    print(f"ID отчёта: {row['run_id']}")
    print(message(report, row['kind'], row['period_start'], row['period_end'],
                  row['snapshot']['evidence']))
    return 0
