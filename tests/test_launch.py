from pathlib import Path
import signal
import unittest
from unittest.mock import Mock, patch

import launch


class LauncherTests(unittest.TestCase):
    @patch('launch.subprocess.run')
    def test_discovers_same_repository_worktrees_with_spaces(self, run):
        run.return_value = Mock(returncode=0, stdout=(
            'worktree /projects/Resume Studio\0HEAD abc\0branch refs/heads/main\0\0'
            'worktree /worktrees/Resume Studio/fix\0HEAD def\0detached\0\0'
        ))
        self.assertEqual(launch.editor_roots(), {
            launch.ROOT, Path('/projects/Resume Studio/src'),
            Path('/worktrees/Resume Studio/fix/src'),
        })

    @patch('launch.subprocess.run', return_value=Mock(returncode=128))
    def test_non_git_checkout_still_recognizes_itself(self, run):
        self.assertEqual(launch.editor_roots(), {launch.ROOT})

    @patch('launch.subprocess.check_output')
    def test_recognizes_worktree_launcher_and_direct_server(self, output):
        root = Path('/worktrees/Resume Studio/fix/src')
        for command in (
            f'/worktrees/Resume Studio/fix/.venv/bin/python3 {root}/launch.py',
            f'python3 {root}/server.py --port 8765',
            'python3 src/launch.py',
        ):
            with self.subTest(command=command):
                output.side_effect = [command, f'p123\nfcwd\nn{root.parent}\n']
                self.assertTrue(launch.is_editor(123, {root}))

    @patch('launch.subprocess.check_output')
    def test_unrelated_server_is_not_an_editor(self, output):
        for command in ('python3 server.py', 'python3 -m http.server 8765',
                        f'python3 {launch.ROOT}/launch.py.bak'):
            with self.subTest(command=command):
                output.side_effect = [command, 'p123\nfcwd\nn/other/app\n']
                self.assertFalse(launch.is_editor(123, {launch.ROOT}))

    def test_restarts_recognized_instance_before_binding(self):
        with patch('launch.STORE'), patch('launch.editor_roots', return_value={launch.ROOT}), \
                patch('launch.listeners', side_effect=[{123}, {123}, set()]), \
                patch('launch.is_editor', return_value=True), \
                patch('launch.os.kill') as kill, patch('launch.time.sleep'), \
                patch('launch.subprocess.run'), patch('launch.ThreadingHTTPServer') as server:
            server.side_effect = lambda *args: (kill.assert_called_once_with(
                123, signal.SIGTERM) or MockServer())
            launch.main()
            server.assert_called_once_with(('127.0.0.1', launch.PORT), launch.Handler)

    def test_does_not_stop_unrelated_application(self):
        with patch('launch.STORE'), patch('launch.editor_roots', return_value={launch.ROOT}), \
                patch('launch.listeners', return_value={123}), \
                patch('launch.is_editor', return_value=False), patch('launch.os.kill') as kill:
            with self.assertRaisesRegex(RuntimeError, 'another application'):
                launch.main()
            kill.assert_not_called()


class MockServer:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def serve_forever(self):
        pass
