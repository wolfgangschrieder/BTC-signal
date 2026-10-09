import argparse
import asyncio
from datetime import datetime
from sqlalchemy import text
from research_os.core.config import get_settings
from research_os.database.session import SessionLocal,engine

def health():
    settings=get_settings()
    try:
        with engine.connect() as connection: connection.execute(text("SELECT 1"))
        print({"environment":settings.environment,"database":"ok"}); return 0
    except Exception as exc:
        print({"environment":settings.environment,"database":f"error: {type(exc).__name__}"}); return 1

def cross_market(start,end,assets):
    from research_os.cross_market.ingestion import CrossMarketIngestionService
    from research_os.cross_market.providers import FREDProvider
    settings=get_settings()
    if not settings.fred_api_key:
        print({"status":"error","reason":"FRED_API_KEY is not configured"})
        return 1
    start_dt=datetime.fromisoformat(start) if start else None
    end_dt=datetime.fromisoformat(end) if end else None
    selected=tuple(x.strip() for x in assets.split(",") if x.strip()) if assets else None
    async def run():
        service=CrossMarketIngestionService(FREDProvider(settings.fred_api_key))
        with SessionLocal() as session:
            total=await service.fetch_and_store(session,start_dt,end_dt,selected)
            session.commit()
            return total
    print({"stored":asyncio.run(run())})
    return 0

def dataset(symbol,start,end,horizon):
    from research_os.cross_market.models import CrossMarketObservation
    from research_os.intelligence.event_repository import ExternalEventRepository
    from research_os.research.research_dataset import ResearchDatasetBuilder
    from research_os.research.research_dataset_repository import ResearchDatasetRepository
    from research_os.research.replay_repository import ReplayRepository

    if not start or not end:
        raise ValueError("--start and --end are required for dataset")
    start_dt=datetime.fromisoformat(start)
    end_dt=datetime.fromisoformat(end)
    horizon_minutes=int(horizon)

    with SessionLocal() as session:
        candles=ReplayRepository().load_candles(session,symbol,start_dt,end_dt)
        decision_times=tuple(c.event_time for c in candles)
        state_rows=session.execute(text("""
            SELECT timestamp, vector
            FROM world.market_state_vectors
            WHERE symbol=:symbol
              AND timestamp>=:start AND timestamp<=:end
              AND point_in_time_available_at<=timestamp
            ORDER BY timestamp
        """),{"symbol":symbol,"start":start_dt,"end":end_dt}).mappings().all()
        features_by_time={}
        for row in state_rows:
            values=(row["vector"] or {}).get("values",row["vector"] or {})
            features_by_time[row["timestamp"]]={
                key: float(value) for key,value in values.items()
                if isinstance(value,(int,float)) and not isinstance(value,bool)
            }

        cross_rows=session.execute(text("""
            SELECT asset,event_time,point_in_time_available_at,value,source,unit
            FROM intelligence.cross_market_observations
            WHERE event_time<=:end AND point_in_time_available_at<=:end
            ORDER BY event_time, asset
        """),{"end":end_dt}).mappings().all()
        cross_market_observations=tuple(
            CrossMarketObservation(
                asset=row["asset"],timestamp=row["event_time"],
                point_in_time_available_at=row["point_in_time_available_at"],
                value=float(row["value"]),source=row["source"],unit=row["unit"] or "raw",
            )
            for row in cross_rows
        )

        external_rows=session.execute(text("""
            SELECT event_id,title,source,event_time,point_in_time_available_at,
                   category,impact,relevance,sentiment,confidence,payload
            FROM intelligence.external_events
            WHERE event_time<=:end AND point_in_time_available_at<=:end
            ORDER BY event_time
        """),{"end":end_dt}).mappings().all()
        external_events=tuple(ExternalEventRepository._to_event(row) for row in external_rows)

        built=ResearchDatasetBuilder().build(
            symbol,decision_times,candles,
            cross_market_observations=cross_market_observations,
            features_by_time=features_by_time,
            external_events=external_events,
            horizon_minutes=horizon_minutes,
        )
        saved=ResearchDatasetRepository().save(session,built)
        session.commit()
    pit_violations=ResearchDatasetBuilder.audit_pit(built,external_events,cross_market_observations)
    print({"dataset_version":built.version,"rows":len(built.rows),"saved":saved,
           "skipped":built.skipped,"pit_violations":len(pit_violations)})
    return 0

def calibration(symbol,start,end):
    from research_os.research.calibration_repository import CalibrationRepository
    with SessionLocal() as session:
        report=CalibrationRepository().evaluate(session,symbol,datetime.fromisoformat(start) if start else None,datetime.fromisoformat(end) if end else None)
    print({"samples":report.samples,"brier":report.brier,"log_loss":report.log_loss,"ece":report.expected_calibration_error,"mce":report.max_calibration_error,"buckets":[{"lower":b.lower,"upper":b.upper,"samples":b.samples,"predicted":b.predicted_mean,"actual":b.actual_rate,"error":b.calibration_error} for b in report.buckets]})
    return 0

def calibration_fit(symbol, direction):
    from datetime import UTC
    from research_os.pipeline.live import LiveSignalService
    from research_os.research.calibration_model import fit_artifact
    from research_os.research.calibration_model_repository import CalibrationModelRepository

    service = LiveSignalService(symbol=symbol, settings=get_settings())
    now = datetime.now(UTC)
    repository = CalibrationModelRepository()
    with SessionLocal() as session:
        rows = repository.load_samples(session, symbol=symbol, direction=direction,
                                       context_id=service.calibration_context, as_of=now)
        try:
            artifact = fit_artifact(rows, symbol=symbol, direction=direction,
                                    context_id=service.calibration_context, now=now,
                                    decision_threshold=service.pipeline.signal.min_probability)
        except ValueError as error:
            print({"accepted":False,"eligible_samples":len(rows),"reason":str(error),
                   "context_id":service.calibration_context})
            return 2
        model_id = repository.save(session, artifact)
        session.commit()
    reasons = artifact.rejection_reasons()
    print({"model_id":model_id,"accepted":not reasons,"target":artifact.target,
           "train":artifact.train.samples,"validation":artifact.validation.samples,
           "test":artifact.test.samples,"metrics":artifact.metrics.model_dump(),"reasons":reasons})
    return 2 if reasons else 0


def regime(symbol,start,end):
    from research_os.research.replay_repository import ReplayRepository
    from research_os.research.regimes import RegimeAnalyzer
    with SessionLocal() as session:
        report=ReplayRepository().run(session,symbol,datetime.fromisoformat(start),datetime.fromisoformat(end))
    analyzed=RegimeAnalyzer().analyze([(x,x.features) for x in report.results])
    print([{"regime":s.regime.value,"signals":s.signals,"resolved":s.resolved,"wins":s.wins,"losses":s.losses,"expired":s.expired,"win_rate":s.win_rate,"avg_return":s.avg_return} for s in analyzed.stats])
    return 0

def replay(symbol,start,end):
    from research_os.research.replay_repository import ReplayRepository
    with SessionLocal() as session:
        report=ReplayRepository().run(session,symbol,datetime.fromisoformat(start),datetime.fromisoformat(end))
    print({"symbol":report.symbol,"dataset_version":report.dataset_version,"signals":report.signals,"resolved":report.resolved,"wins":report.wins,"losses":report.losses,"expired":report.expired,"win_rate":report.win_rate,"brier":report.brier,"log_loss":report.log_loss})
    return 0

def state(symbol=None,history=False,timestamp=None,compare=None):
    from research_os.market.state_repository import MarketStateRepository
    with SessionLocal() as session:
        repo=MarketStateRepository()
        target_symbol=symbol or "BTCUSDT"
        if compare:
            left=datetime.fromisoformat(timestamp) if timestamp else datetime.now().astimezone()
            right=datetime.fromisoformat(compare)
            result=repo.compare(session,target_symbol,left,right)
            print(result or {"status":"not_found"})
            return 0
        if timestamp:
            row=repo.at(session,target_symbol,datetime.fromisoformat(timestamp))
            print(dict(row) if row else {"status":"not_found"})
            return 0
        if history:
            print([dict(row) for row in repo.history(session,target_symbol)])
            return 0
        row=repo.history(session,target_symbol,1)
        print(dict(row[0]) if row else {"status":"not_found"})
    return 0

def bounded_report_integer(value, lower, upper):
    parsed = int(value)
    if not lower <= parsed <= upper:
        raise argparse.ArgumentTypeError(f"value must be between {lower} and {upper}")
    return parsed


def observation_report(symbol, hours, limit):
    import json
    from research_os.research.observation_report import build_report
    settings = get_settings()
    with SessionLocal() as session:
        report = build_report(session, symbol=symbol, hours=hours, limit=limit,
                              threshold=settings.signal_min_probability,
                              calibrated_models_configured=bool(settings.calibration_model_ids.strip()))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main():
    parser=argparse.ArgumentParser(prog="research-os")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("health"); sub.add_parser("live"); sub.add_parser("auditor")
    cm=sub.add_parser("cross-market")
    cm.add_argument("--start")
    cm.add_argument("--end")
    cm.add_argument("--assets",help="comma-separated FRED assets; default: all configured assets")
    obs=sub.add_parser("observation-report")
    obs.add_argument("--symbol", default="BTCUSDT")
    obs.add_argument("--hours", type=lambda value: bounded_report_integer(value,1,168), default=24)
    obs.add_argument("--limit", type=lambda value: bounded_report_integer(value,1,5000), default=1000)
    st=sub.add_parser("state")
    st.add_argument("--symbol",default="BTCUSDT")
    st.add_argument("--history",action="store_true")
    st.add_argument("--timestamp")
    st.add_argument("--compare",help="second timestamp to compare with --timestamp or current time")
    rp=sub.add_parser("replay"); rp.add_argument("--symbol",default="BTCUSDT"); rp.add_argument("--start",required=True); rp.add_argument("--end",required=True)
    cp=sub.add_parser("calibration"); cp.add_argument("--symbol",default=None); cp.add_argument("--start",default=None); cp.add_argument("--end",default=None)
    fit=sub.add_parser("calibration-fit"); fit.add_argument("--symbol",default="BTCUSDT"); fit.add_argument("--direction",required=True,choices=("long","short"))
    ds=sub.add_parser("dataset"); ds.add_argument("--symbol",default="BTCUSDT"); ds.add_argument("--start",required=True); ds.add_argument("--end",required=True); ds.add_argument("--horizon",default="60")
    rg=sub.add_parser("regime"); rg.add_argument("--symbol",default="BTCUSDT"); rg.add_argument("--start",required=True); rg.add_argument("--end",required=True)
    args=parser.parse_args()
    if args.command=="observation-report": raise SystemExit(observation_report(args.symbol,args.hours,args.limit))
    if args.command=="health": raise SystemExit(health())
    if args.command=="state": raise SystemExit(state(args.symbol,args.history,args.timestamp,args.compare))
    if args.command=="auditor":
        from research_os.auditor.runtime import main as auditor_main
        auditor_main()
    if args.command=="live":
        from research_os.pipeline.runtime import main as live_main
        live_main()
    if args.command=="cross-market": raise SystemExit(cross_market(args.start,args.end,args.assets))
    if args.command=="replay": raise SystemExit(replay(args.symbol,args.start,args.end))
    if args.command=="calibration-fit": raise SystemExit(calibration_fit(args.symbol,args.direction))
    if args.command=="calibration": raise SystemExit(calibration(args.symbol,args.start,args.end))
    if args.command=="dataset": raise SystemExit(dataset(args.symbol,args.start,args.end,args.horizon))
    if args.command=="regime": raise SystemExit(regime(args.symbol,args.start,args.end))
if __name__=="__main__": main()
