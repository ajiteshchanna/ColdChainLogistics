import json
import subprocess
import sys
import unittest
from pathlib import Path


class HealthCheckTests(unittest.TestCase):
    def test_offline_health_check_returns_machine_readable_success(self):
        project_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "scripts\\health_check.py"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checks"]["configuration"], "ok")


if __name__ == "__main__":
    unittest.main()
