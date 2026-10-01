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

def calibration(symbol,start,end):
    from research_os.research.calibration_repository import CalibrationRepository
    with SessionLocal() as session:
        report=CalibrationRepository().evaluate(session,symbol,datetime.fromisoformat(start) if start else None,datetime.fromisoformat(end) if end else None)
    print({"samples":report.samples,"brier":report.brier,"log_loss":report.log_loss,"ece":report.expected_calibration_error,"mce":report.max_calibration_error,"buckets":[{"lower":b.lower,"upper":b.upper,"samples":b.samples,"predicted":b.predicted_mean,"actual":b.actual_rate,"error":b.calibration_error} for b in report.buckets]})
    return 0

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

def main():
    parser=argparse.ArgumentParser(prog="research-os")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("health"); sub.add_parser("live")
    cm=sub.add_parser("cross-market")
    cm.add_argument("--start")
    cm.add_argument("--end")
    cm.add_argument("--assets",help="comma-separated FRED assets; default: all configured assets")
    st=sub.add_parser("state")
    st.add_argument("--symbol",default="BTCUSDT")
    st.add_argument("--history",action="store_true")
    st.add_argument("--timestamp")
    st.add_argument("--compare",help="second timestamp to compare with --timestamp or current time")
    rp=sub.add_parser("replay"); rp.add_argument("--symbol",default="BTCUSDT"); rp.add_argument("--start",required=True); rp.add_argument("--end",required=True)
    cp=sub.add_parser("calibration"); cp.add_argument("--symbol",default=None); cp.add_argument("--start",default=None); cp.add_argument("--end",default=None)
    rg=sub.add_parser("regime"); rg.add_argument("--symbol",default="BTCUSDT"); rg.add_argument("--start",required=True); rg.add_argument("--end",required=True)
    args=parser.parse_args()
    if args.command=="health": raise SystemExit(health())
    if args.command=="state": raise SystemExit(state(args.symbol,args.history,args.timestamp,args.compare))
    if args.command=="live":
        from research_os.pipeline.runtime import main as live_main
        live_main()
    if args.command=="cross-market": raise SystemExit(cross_market(args.start,args.end,args.assets))
    if args.command=="replay": raise SystemExit(replay(args.symbol,args.start,args.end))
    if args.command=="calibration": raise SystemExit(calibration(args.symbol,args.start,args.end))
    if args.command=="regime": raise SystemExit(regime(args.symbol,args.start,args.end))
if __name__=="__main__": main()
