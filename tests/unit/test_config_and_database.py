import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import ConfigurationError, ServiceUnavailableError, load_config
from src.database import validate_telemetry_query
from src.agent_tools import _get_config, query_telemetry_db, search_compliance_sop
from src.orchestrator import create_agent, get_agent


class ConfigurationTests(unittest.TestCase):
    def test_load_config_requires_admin_credentials_when_requested(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_config(
                    Path.cwd(),
                    require_admin=True,
                    load_environment=False,
                )

    def test_load_config_parses_port_and_timeout(self):
        values = {
            "SQL_SERVER_HOST": "localhost",
            "SQL_SERVER_PORT": "1444",
            "SQL_CONNECT_TIMEOUT_SECONDS": "7",
            "SQL_AGENT_PASSWORD": "agent-secret",
        }
        with patch.dict(os.environ, values, clear=True):
            config = load_config(Path.cwd(), load_environment=False)

        self.assertEqual(config.sql_port, 1444)
        self.assertEqual(config.sql_timeout_seconds, 7)
        self.assertEqual(config.sql_agent_password, "agent-secret")

    def test_load_config_without_env_file_uses_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(Path(directory), load_environment=True)

        self.assertEqual(config.reefertwin_mode, "local")
        self.assertEqual(config.sql_host, "localhost")
        self.assertEqual(config.sql_agent_password, "")

    def test_environment_overrides_streamlit_secrets_and_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "SQL_SERVER_HOST=dotenv-host\nREEFERTWIN_MODE=local\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"SQL_SERVER_HOST": "environment-host"},
                clear=True,
            ):
                config = load_config(
                    root,
                    secrets={
                        "SQL_SERVER_HOST": "secret-host",
                        "REEFERTWIN_MODE": "demo",
                    },
                )

        self.assertEqual(config.sql_host, "environment-host")
        self.assertEqual(config.reefertwin_mode, "demo")

    def test_load_config_reads_local_dotenv_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "SQL_SERVER_HOST=dotenv-host\nSQL_AGENT_PASSWORD=dotenv-secret\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(root)

        self.assertEqual(config.sql_host, "dotenv-host")
        self.assertEqual(config.sql_agent_password, "dotenv-secret")

    def test_imports_do_not_initialize_external_services(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import src.agent_tools, src.orchestrator; print('ok')",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), "ok")

    def test_demo_mode_reports_ai_as_unavailable(self):
        get_agent.cache_clear()
        with patch.dict(
            os.environ,
            {"REEFERTWIN_MODE": "demo"},
            clear=True,
        ):
            with self.assertRaises(ServiceUnavailableError):
                get_agent()
        get_agent.cache_clear()

    def test_optional_tools_report_missing_services_without_secrets(self):
        _get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            database_result = query_telemetry_db.invoke(
                "SELECT TOP 1 Latitude FROM FDE_VIEWS.VW_ACTIVE_FLEET"
            )
            sop_result = search_compliance_sop.invoke("temperature limits")
        _get_config.cache_clear()

        self.assertIn('"status": "error"', database_result)
        self.assertIn('"status": "degraded"', sop_result)
        self.assertNotIn("password", database_result.lower())
        self.assertNotIn("password", sop_result.lower())

    def test_missing_ollama_is_typed_as_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(Path.cwd(), load_environment=False)
            with patch.dict(sys.modules, {"langchain_ollama": None}):
                with self.assertRaises(ServiceUnavailableError):
                    create_agent(config)


class TelemetryQueryValidationTests(unittest.TestCase):
    def test_accepts_select_from_semantic_view(self):
        self.assertIsNone(
            validate_telemetry_query(
                "SELECT TOP 2 Latitude FROM FDE_VIEWS.VW_ACTIVE_FLEET"
            )
        )

    def test_rejects_non_select_and_other_objects(self):
        self.assertIsNotNone(
            validate_telemetry_query("UPDATE FDE_VIEWS.VW_ACTIVE_FLEET SET Latitude = 0")
        )
        self.assertIsNotNone(
            validate_telemetry_query("SELECT * FROM dbo.TBL_SC_FLEET_HIST_RAW")
        )

    def test_rejects_comments_and_multiple_statements(self):
        self.assertIsNotNone(
            validate_telemetry_query(
                "SELECT * FROM FDE_VIEWS.VW_ACTIVE_FLEET; SELECT 1"
            )
        )
        self.assertIsNotNone(
            validate_telemetry_query(
                "SELECT * FROM FDE_VIEWS.VW_ACTIVE_FLEET -- bypass"
            )
        )


if __name__ == "__main__":
    unittest.main()
