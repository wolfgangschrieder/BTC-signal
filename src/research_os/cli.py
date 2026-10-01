import argparse
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

def replay(symbol,start,end):
    from research_os.research.replay_repository import ReplayRepository
    with SessionLocal() as session:
        report=ReplayRepository().run(session,symbol,datetime.fromisoformat(start),datetime.fromisoformat(end))
    print({"symbol":report.symbol,"dataset_version":report.dataset_version,"signals":report.signals,"resolved":report.resolved,"wins":report.wins,"losses":report.losses,"expired":report.expired,"win_rate":report.win_rate,"brier":report.brier,"log_loss":report.log_loss})
    return 0

def main():
    parser=argparse.ArgumentParser(prog="research-os"); sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("health"); sub.add_parser("live")
    rp=sub.add_parser("replay"); rp.add_argument("--symbol",default="BTCUSDT"); rp.add_argument("--start",required=True); rp.add_argument("--end",required=True)
    args=parser.parse_args()
    if args.command=="health": raise SystemExit(health())
    if args.command=="live":
        from research_os.pipeline.runtime import main as live_main
        live_main()
    if args.command=="replay": raise SystemExit(replay(args.symbol,args.start,args.end))
if __name__=="__main__": main()
