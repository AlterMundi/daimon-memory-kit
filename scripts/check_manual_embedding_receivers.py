"""Exercise selected manual DMK receivers from an existing Incus maintenance job."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from codex_coordinator import checkpoint


# Executed as the child account. Only a closed result leaves the container.
CHECK = r"""
import json, os, subprocess
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
command = [str(Path.home() / '.local/bin/dmk'), 'memoryctl.py']
def read(*argv):
    result = subprocess.run(command + list(argv), timeout=12, capture_output=True,
                            check=True, text=True)
    return json.loads(result.stdout)
try:
    config = read('embed-config')
    if (config['default_provider'] != 'model2vec'
            or not config['providers']['model2vec']['configured']):
        raise ValueError('offline encoder is not selected')
    selection = ('--provider', 'model2vec', '--model', config['default_model'])
    probe = ('semantic-search', '--query', 'Encuadernar cuadernos artesanales', '--limit', '1')
    if not isinstance(read(*probe, *selection), list):
        raise ValueError('invalid reader result')
    count = read('embed-backfill', '--limit', '16', *selection)['processed']
    if count and not read(*probe, *selection):
        raise ValueError('repair did not make the new vectors reachable')
    print(json.dumps({'state': 'healthy', 'repaired': count}))
except (OSError, ValueError, KeyError, subprocess.SubprocessError):
    print(json.dumps({'state': 'unavailable'}))
"""


def inspect(config, *, run=subprocess.run):
    targets = [target for target in config['targets'] if target['instance'] is not None]
    if not 1 <= len(targets) <= 8 or len({t['id'] for t in targets}) != len(targets):
        raise ValueError('bounded unique maintenance targets required')
    result = {}
    for target in targets:
        name = target['id']
        instance = target['instance']
        if instance != f'dm-{name}' or not re.fullmatch(r'dm-[a-z0-9-]{1,48}', instance):
            raise ValueError('existing named receiver required')
        try:
            process = run(['/usr/bin/incus', 'exec', instance, '--', '/usr/sbin/runuser',
                           '-u', 'agent', '--', '/usr/bin/python3', '-I', '-B', '-c', CHECK],
                          capture_output=True, text=True, timeout=42, check=True)
            value = json.loads(process.stdout)
            if (value.get('state') != 'healthy' or type(value.get('repaired')) is not int
                    or not 0 <= value['repaired'] <= 16):
                raise ValueError('invalid or failed option')
            result[name] = dict(state='healthy', repaired=value['repaired'])
        except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
            result[name] = dict(state='unavailable')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(json.loads(args.inventory.read_bytes()))
    checkpoint(args.receipt, result)
    print(json.dumps(result))
    return 0 if all(row['state'] == 'healthy' for row in result.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
