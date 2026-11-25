"""Check and repair the selected offline embedding space without advancing worker state."""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import time
import sqlite3

from capture_inbox import Inbox
from capturectl import digest
from codex_coordinator import checkpoint
from memory_runtime import load_memory, profile


CANARY_PASSAGES = [
    'El taller artesanal enseña a encuadernar cuadernos con tapas de tela.',
    'La luna orbita alrededor de la Tierra cada veintisiete días.',
]
CANARY_QUERY = 'Aprender encuadernación artesanal de cuadernos'


def probe(memory, space):
    # A scheduled check must not download a model or send records to an API.
    if space['provider'] != 'model2vec':
        raise ValueError('offline Model2Vec selection required')
    passages = memory.embed_texts(**embed_args(space), texts=CANARY_PASSAGES, input_type='passage')
    query, = memory.embed_texts(**embed_args(space), texts=[CANARY_QUERY], input_type='query')
    dimensions = len(query)
    if not dimensions or (space['output_dimensionality'] not in (None, dimensions)):
        raise ValueError('invalid query dimensions')
    for vector in [*passages, query]:
        if len(vector) != dimensions or not all(map(math.isfinite, vector)) or not any(vector):
            raise ValueError('invalid vector')
    expected, distractor = (memory.cosine_similarity(query, row) for row in passages)
    if expected <= distractor:
        raise ValueError('canary did not rank its evidence first')
    return dimensions


def embed_args(space):
    return {key: space[key] for key in ('provider', 'model', 'output_dimensionality')}


def inspect(memory, *, repair_limit):
    space = memory.embeddings_runtime_config()
    dimensions = probe(memory, space)
    with memory.connect() as con:
        indexed = con.execute(
            'SELECT count(*), min(dims), max(dims) FROM chapter_embeddings WHERE provider=? AND model=?',
            (space['provider'], space['model']),
        ).fetchone()
    if indexed[0] and (indexed[1], indexed[2]) != (dimensions, dimensions):
        raise ValueError('index and model dimensions differ')
    selection = {k: space[k] for k in ('provider', 'model')}
    repaired = 0
    pending = bool(memory.embedding_candidates(**selection, limit=1))
    if pending and repair_limit:
        repaired = memory.backfill_embeddings(**selection, limit=repair_limit)['processed']
        pending = bool(memory.embedding_candidates(**selection, limit=1))
    if indexed[0] or repaired:
        if not memory.semantic_search(CANARY_QUERY, limit=1):
            raise ValueError('selected reader returned no indexed evidence')
    return {'state': 'pending' if pending else 'healthy', 'dimensions': dimensions,
            'repaired': repaired, 'missing_or_stale': pending}


def check(config, *, repair_limit=16):
    binding = json.loads(Path(config['binding']).read_bytes())
    if any(binding.get(key) != config['context'][key] for key in ('subject', 'source_instance')):
        raise ValueError('capture binding differs from worker context')
    inbox_path = Path(config['inbox'])
    if not inbox_path.is_file() or (binding.get('inbox') and Path(binding['inbox']).resolve() != inbox_path.resolve()):
        raise ValueError('existing bound capture inbox required')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    memory = load_memory(config)
    inbox = Inbox(inbox_path, binding)
    with open(str(inbox_path) + '.producer.lock', 'a+b') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            repair_limit = 0
        with inbox.connect() as con:
            owner_row = con.execute('SELECT value FROM producer_owner').fetchone()
        owner = json.loads(owner_row[0]) if owner_row else {}
        if (owner.get('database') != str(Path(memory.DB_PATH).resolve())
                or owner.get('state_dir') != str(Path(config['state_dir']).resolve())
                or owner.get('capture_binding') != digest(binding)):
            raise ValueError('index work binding differs')
        try:
            return inspect(memory, repair_limit=repair_limit)
        except (OSError, ValueError, memory.EmbeddingBackendError, sqlite3.Error, SystemExit):
            return {'state': 'unavailable'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(profile(args.profile))
    except (OSError, ValueError, sqlite3.Error, SystemExit):
        result = {'state': 'unavailable'}
    result = dict(result, checked_at=int(time.time()))
    checkpoint(args.receipt, result)
    print(json.dumps(result))
    return 0 if result['state'] == 'healthy' else 2


if __name__ == '__main__':
    raise SystemExit(main())
