import argparse
from sqlalchemy import text
from research_os.core.config import get_settings
from research_os.database.session import engine

def health() -> int:
    settings = get_settings()
    result = {"environment": settings.environment, "database": "unknown"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        result["database"] = "ok"
    except Exception as exc:
        result["database"] = f"error: {type(exc).__name__}"
    print(result)
    return 0 if result["database"] == "ok" else 1

def main() -> None:
    parser = argparse.ArgumentParser(prog="research-os")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    args = parser.parse_args()
    if args.command == "health":
        raise SystemExit(health())

if __name__ == "__main__":
    main()
