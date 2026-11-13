import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import ConfigurationError, load_config
from src.database import validate_telemetry_query


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
