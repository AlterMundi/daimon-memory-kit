import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_manual_embedding_receivers import inspect


def test_checks_local_bindings_and_retains_failed_body():
    seen = []
    def run(command, **options):
        seen.append(command[2])
        assert options['timeout'] == 42
        if command[2] == 'dm-birch':
            raise subprocess.TimeoutExpired(command, 42)
        return subprocess.CompletedProcess(command, 0, json.dumps(dict(state='healthy', repaired=2)), '')
    config = {'targets': [dict(id='host', instance=None), dict(id='elm', instance='dm-elm'),
                          dict(id='birch', instance='dm-birch')]}
    assert inspect(config, run=run) == {'elm': dict(state='healthy', repaired=2),
                                      'birch': dict(state='unavailable')}
    assert seen == ['dm-elm', 'dm-birch']
