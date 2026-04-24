#!/usr/bin/env python3
"""
Embedding backfill micro-batch worker (Boswell v4.0).
Run via Railway cron service every 5 minutes.

Picks up blobs and candidates with NULL embeddings, generates embeddings
via OpenAI, writes them back. Decouples embedding latency from the write path.

CC/CW consensus March 30 2026: 5-minute cadence, not nightly.
Steve's burst workflow needs <5min semantic blind spot, not 24 hours.

Cadence: */5 * * * * (every 5 minutes)
Batch size: 20 blobs + 20 candidates per cycle
Budget: 30 second max runtime
"""

import os
import sys
import json
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)

MAX_RUNTIME = 30
BATCH_SIZE = 20


def main():
    """Run embedding backfill micro-batch."""
    url = f"{BOSWELL_URL}/v2/embeddings/backfill"

    try:
        response = requests.post(
            url,
            json={'batch_size': BATCH_SIZE},
            timeout=MAX_RUNTIME
        )
        response.raise_for_status()
        data = response.json()

        blobs_filled = data.get('blobs_filled', 0)
        candidates_filled = data.get('candidates_filled', 0)
        errors = data.get('errors', 0)
        duration = data.get('duration_ms', 0)

        total = blobs_filled + candidates_filled
        # Fix 3: always log every cron run, regardless of work done.
        # Sacred rule c36afb57: "NO SILENT FAILURES — exit 0 means success not silence,
        # swallowed exceptions banned." The Mar 31 → Apr 4 2026 silent failure went
        # 96 hours / 288 cron runs without anyone noticing because of the previous
        # `if total > 0 or errors > 0` guard. Always log so Railway captures the run.
        print(f"[BACKFILL] {blobs_filled} blobs + {candidates_filled} candidates embedded in {duration}ms ({errors} errors)")

        # Exit 0 unless errors outnumber successes during actual work.
        # Persistent bad blobs (e.g. empty content) shouldn't fail every run.
        sys.exit(1 if total > 0 and errors > total else 0)

    except requests.Timeout:
        print(f"[BACKFILL] TIMEOUT: Exceeded {MAX_RUNTIME}s", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[BACKFILL] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
