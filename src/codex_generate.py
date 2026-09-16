"""Subscription-authenticated structured generation through the local Codex CLI."""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


class GenerationCancelled(Exception):
    pass


class CodexRunner:
    def __call__(self, prompt, keys, cancel):
        executable = shutil.which('codex')
        if not executable:
            raise RuntimeError('Codex CLI is missing. Install it and sign in with ChatGPT, then retry.')
        env = {k: v for k, v in os.environ.items() if k not in ('OPENAI_API_KEY', 'CODEX_API_KEY')}
        login = subprocess.run([executable, 'login', 'status'], capture_output=True, text=True, env=env, timeout=20)
        if login.returncode or 'ChatGPT' not in login.stdout + login.stderr:
            raise RuntimeError('Sign in to Codex with your ChatGPT account, then retry. API billing is not enabled for this workflow.')
        schema = {'type': 'object', 'properties': {key: {'type': 'string'} for key in keys},
                  'required': list(keys), 'additionalProperties': False}
        with tempfile.TemporaryDirectory(prefix='resume-generation-') as folder:
            root = Path(folder)
            (root/'schema.json').write_text(json.dumps(schema))
            (root/'prompt.txt').write_text(prompt)
            command = [executable, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                       '--sandbox', 'read-only', '-c', 'approval_policy="never"',
                       '-c', 'features.shell_tool=false', '-c', 'web_search="disabled"',
                       '--output-schema', str(root/'schema.json'), '-o', str(root/'response.json'), '-']
            with (root/'prompt.txt').open() as source, (root/'process.log').open('w') as log:
                process = subprocess.Popen(command, stdin=source, stdout=log, stderr=log, cwd=root, env=env)
                deadline = time.monotonic() + 600
                try:
                    while process.poll() is None:
                        if cancel.wait(.25):
                            raise GenerationCancelled()
                        if time.monotonic() > deadline:
                            raise RuntimeError('Generation timed out. Retry to continue from the last completed step.')
                    if cancel.is_set():
                        raise GenerationCancelled()
                    if process.returncode or not (root/'response.json').exists():
                        detail = (root/'process.log').read_text(errors='replace').lower()
                        if any(word in detail for word in ('usage limit', 'rate limit', 'quota', '429')):
                            raise RuntimeError('Your Codex usage limit was reached. Wait for it to reset, then retry.')
                        if any(word in detail for word in ('unauthorized', '401', 'token expired')):
                            raise RuntimeError('Your Codex sign-in expired. Sign in with ChatGPT and retry.')
                        raise RuntimeError('Codex could not complete generation. Check your Codex sign-in and connection, then retry.')
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
            result = json.loads((root/'response.json').read_text())
            if set(result) != set(keys) or any(not isinstance(value, str) for value in result.values()):
                raise ValueError('Codex returned an invalid response. Retry generation.')
            return result
