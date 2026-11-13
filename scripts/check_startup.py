"""Validate Phase 0 runtime configuration and optionally SQL connectivity."""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import ConfigurationError, load_config
from src.database import create_sql_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-sql",
        action="store_true",
        help="Open a SQL connection and run SELECT 1.",
    )
    args = parser.parse_args()

    try:
        config = load_config(project_root, require_agent=True)
        print(
            f"Configuration valid: SQL Server {config.sql_host}:{config.sql_port}, "
            f"LLM {config.agent_llm}."
        )
        if args.check_sql:
            from sqlalchemy import text

            engine = create_sql_engine(config)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("SQL connectivity check passed.")
    except (ConfigurationError, ValueError, OSError) as exc:
        print(f"Startup validation failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Startup dependency check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
