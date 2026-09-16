import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from bootstrap import prepare


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'requirements.txt').write_text('jsonschema>=4.18,<5\n')
        self.python = self.root / '.venv/bin/python3'
        self.stamp = self.root / '.venv/.requirements.sha256'

    def existing_environment(self):
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        self.stamp.write_text(hashlib.sha256(
            (self.root / 'requirements.txt').read_bytes()).hexdigest())

    @patch('bootstrap.subprocess.run')
    def test_first_launch_creates_environment_and_installs_before_check(self, run):
        def result(command, **kwargs):
            if 'venv' in command:
                self.python.parent.mkdir(parents=True)
                self.python.touch()
            return Mock(returncode=0)
        run.side_effect = result
        self.assertEqual(prepare(self.root), self.python)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn('venv', commands[0])
        self.assertIn('pip', commands[1])
        self.assertEqual(commands[2][1], '-c')
        self.assertTrue(self.stamp.exists())

    @patch('bootstrap.subprocess.run', return_value=Mock(returncode=0))
    def test_healthy_launch_does_not_install_or_need_network(self, run):
        self.existing_environment()
        prepare(self.root)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][1], '-c')

    @patch('bootstrap.subprocess.run')
    def test_missing_module_repairs_environment(self, run):
        self.existing_environment()
        run.side_effect = [Mock(returncode=1), Mock(returncode=0), Mock(returncode=0)]
        prepare(self.root)
        self.assertIn('pip', run.call_args_list[1].args[0])

    @patch('bootstrap.subprocess.run', return_value=Mock(returncode=0))
    def test_changed_requirements_install_updates(self, run):
        self.existing_environment()
        (self.root / 'requirements.txt').write_text('jsonschema>=4.18,<5\ncertifi\n')
        prepare(self.root)
        self.assertIn('pip', run.call_args_list[0].args[0])

    @patch('bootstrap.subprocess.run')
    def test_failed_install_is_not_marked_ready(self, run):
        self.existing_environment()
        self.stamp.unlink()
        run.side_effect = subprocess.CalledProcessError(1, 'pip')
        with self.assertRaises(subprocess.CalledProcessError):
            prepare(self.root)
        self.assertFalse(self.stamp.exists())
