"""Prepare the app's isolated Python environment before starting the server."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
IMPORT_CHECK = 'import jsonschema, certifi, PIL, pypdfium2'


def prepare(root=ROOT):
    environment = root / '.venv'
    python = environment / 'bin' / 'python3'
    requirements = root / 'requirements.txt'
    stamp = environment / '.requirements.sha256'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not python.exists():
        print('Creating Resume Studio Python environment…', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
    ready = (stamp.exists() and stamp.read_text() == fingerprint)
    if ready:
        ready = subprocess.run(
            [str(python), '-c', IMPORT_CHECK], capture_output=True,
        ).returncode == 0
    if not ready:
        print('Installing Resume Studio dependencies…', flush=True)
        subprocess.run([
            str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
            '-r', str(requirements),
        ], check=True)
        subprocess.run([str(python), '-c', IMPORT_CHECK], check=True)
        stamp.write_text(fingerprint)
    return python


if __name__ == '__main__':
    try:
        python = prepare()
        os.execv(str(python), [str(python), str(ROOT / 'src' / 'launch.py')])
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemExit(
            f'Could not prepare Resume Studio dependencies: {error}\n'
            'Check your internet connection and run start.command again.'
        )
