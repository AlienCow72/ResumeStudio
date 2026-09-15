"""Restart this editor on its fixed local port, then open the browser."""
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from server import Handler, ThreadingHTTPServer, STORE

ROOT = Path(__file__).resolve().parent
PORT = 8765


def listeners():
    result = subprocess.run(
        ['/usr/sbin/lsof', '-nP', f'-iTCP:{PORT}', '-sTCP:LISTEN', '-t'],
        capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError('Unable to identify the process using port 8765.')
    return {int(pid) for pid in result.stdout.split()}


def is_editor(pid):
    command = subprocess.check_output(
        ['/bin/ps', '-p', str(pid), '-o', 'command='], text=True,
    ).strip()
    cwd_output = subprocess.check_output(
        ['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], text=True,
    )
    cwd = next((Path(line[1:]) for line in cwd_output.splitlines() if line.startswith('n')), None)
    if cwd is None:
        return False
    # ps does not quote paths containing spaces; accept exact absolute script
    # paths as well as relative arguments resolved against the process cwd.
    for name in ('server.py', 'launch.py'):
        script = ROOT / name
        if str(script) in command:
            return True
        for argument in shlex.split(command):
            if argument.endswith(name) and (cwd / argument).resolve() == script:
                return True
    return False


def main():
    STORE.initialize()
    existing = listeners()
    if any(not is_editor(pid) for pid in existing):
        raise RuntimeError('Port 8765 belongs to another application; it was not stopped.')
    for pid in existing:
        print(f'Stopping existing resume editor (PID {pid})…', flush=True)
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
    while listeners():
        if time.monotonic() >= deadline:
            raise RuntimeError('The existing editor did not stop within 10 seconds. Please close its terminal and retry.')
        time.sleep(0.1)
    # Bind before opening the browser so the URL is ready to accept requests.
    with ThreadingHTTPServer(('127.0.0.1', PORT), Handler) as http:
        url = f'http://127.0.0.1:{PORT}'
        print(f'Resume editor: {url}', flush=True)
        subprocess.run(['/usr/bin/open', url], check=False)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f'Could not start resume editor: {error}')
