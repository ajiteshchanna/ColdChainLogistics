"""Emit a machine-readable application health result."""

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import ConfigurationError, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-sql",
        action="store_true",
        help="Also execute SELECT 1 against SQL Server.",
    )
    args = parser.parse_args()
    result: dict[str, object] = {
        "status": "ok",
        "service": "reefertwin",
        "checks": {},
    }
    try:
        config = load_config(project_root, require_agent=args.check_sql)
        result["checks"]["configuration"] = "ok"
        result["llm"] = config.agent_llm
        if args.check_sql:
            from sqlalchemy import text
            from src.database import create_sql_engine

            engine = create_sql_engine(config)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            result["checks"]["sql"] = "ok"
    except (ConfigurationError, ValueError, OSError) as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
