import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import verify_deploy


class DeploymentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'public').mkdir()
        for name in ('data.js', 'index.html', 'cdcp.html', 'cbrics.html', 'report.html'):
            (self.root / 'public' / name).write_bytes(b'current bundle')
        self.clock = 0

    def sleep(self, seconds):
        self.clock += seconds

    def response(self, current):
        class Response:
            content = b'current bundle' if current else b'previous bundle'
            def raise_for_status(self):
                pass
        return Response()

    def run_verification(self, timeout, ready_at):
        with patch.object(verify_deploy, 'BASE_DIR', self.root), \
             patch.object(verify_deploy.time, 'monotonic', side_effect=lambda: self.clock), \
             patch.object(verify_deploy.time, 'sleep', side_effect=self.sleep), \
             patch.object(verify_deploy.requests, 'get', side_effect=lambda *a, **k: self.response(self.clock >= ready_at)):
            return verify_deploy.verify(timeout)

    def test_delayed_deployment_succeeds_within_fifteen_minutes(self):
        # Reproduces the observed deployment taking nearly nine minutes.
        self.assertTrue(self.run_verification(900, 520))
        self.assertEqual(self.clock, 520)

    def test_old_ninety_second_budget_would_fail(self):
        self.assertFalse(self.run_verification(90, 520))
        self.assertEqual(self.clock, 90)

    def test_stale_production_still_fails(self):
        self.assertFalse(self.run_verification(25, 1000))
        self.assertEqual(self.clock, 25)

    def test_invalid_timeout_fails(self):
        with self.assertRaises(ValueError):
            verify_deploy.verify(0)


if __name__ == '__main__':
    unittest.main()
