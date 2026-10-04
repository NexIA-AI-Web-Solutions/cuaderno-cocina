import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.cuaderno import process_supervisor as subject


class ProcessSupervisorTests(unittest.TestCase):
    def test_daemon_exit_terminates_peer_and_propagates_failure(self):
        for exit_code, expected in ((6, 6), (0, 1)):
            with self.subTest(exit_code=exit_code):
                children = []
                real_popen = subprocess.Popen

                def launch(command):
                    child = real_popen(command)
                    children.append(child)
                    return child

                with patch.object(subject.subprocess, "Popen", side_effect=launch):
                    status = subject.supervise([
                        [sys.executable, "-c", f"import time; time.sleep(.2); raise SystemExit({exit_code})"],
                        [sys.executable, "-c", "import time; time.sleep(60)"],
                    ], grace_seconds=2)
                self.assertEqual(status, expected)
                self.assertEqual(len(children), 2)
                self.assertTrue(all(child.poll() is not None for child in children))

    def test_startup_failure_reaps_already_started_service(self):
        real_popen = subprocess.Popen
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"])
        with patch.object(subject.subprocess, "Popen", side_effect=[child, OSError("missing executable")]):
            with self.assertRaises(OSError):
                subject.supervise([["first"], ["second"]], grace_seconds=2)
        self.assertIsNotNone(child.poll())
