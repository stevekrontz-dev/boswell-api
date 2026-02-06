#!/usr/bin/env python3
"""
Nightly maintenance cron worker (Boswell v4.0).
Run via Railway cron service.
Cadence: Daily at 5am UTC (midnight EST)
Budget: 5 minute max runtime

Runs: trail decay + candidate cleanup + consolidation + centroid refresh
"""

import os
import sys
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)

# Max runtime in seconds (5 minutes)
MAX_RUNTIME = 300

def main():
    """Run nightly maintenance cycle."""
    url = f"{BOSWELL_URL}/v2/nightly"

    print(f"[NIGHTLY] Starting maintenance at {url}")

    try:
        response = requests.post(
            url,
            json={},
            timeout=MAX_RUNTIME
        )
        data = response.json()

        status = data.get('status', 'unknown')
        duration = data.get('duration_ms', 0)
        results = data.get('results', {})

        print(f"[NIGHTLY] {status} in {duration}ms")

        # Trail decay results
        trail = results.get('trail_decay', {})
        if 'error' not in trail:
            processed = trail.get('trails_processed', 0)
            print(f"[NIGHTLY] Trails decayed: {processed}")
        else:
            print(f"[NIGHTLY] Trail decay error: {trail['error']}", file=sys.stderr)

        # Candidate cleanup results
        cleanup = results.get('candidate_cleanup', {})
        if 'error' not in cleanup:
            expired = cleanup.get('expired', 0)
            deleted = cleanup.get('hard_deleted', 0)
            print(f"[NIGHTLY] Candidates expired: {expired}, hard-deleted: {deleted}")
        else:
            print(f"[NIGHTLY] Cleanup error: {cleanup['error']}", file=sys.stderr)

        # Consolidation results
        consol = results.get('consolidation', {})
        if 'error' not in consol:
            evaluated = consol.get('candidates_evaluated', 0)
            promoted = consol.get('candidates_promoted', 0)
            print(f"[NIGHTLY] Consolidation: {evaluated} evaluated, {promoted} promoted")
            if promoted > 0:
                commits = consol.get('promoted_commits', [])
                print(f"[NIGHTLY] Promoted commits: {commits}")
        else:
            print(f"[NIGHTLY] Consolidation error: {consol['error']}", file=sys.stderr)

        # Check for any errors
        has_errors = any('error' in results.get(k, {}) for k in results)
        if has_errors:
            sys.exit(1)

        sys.exit(0)

    except requests.Timeout:
        print(f"[NIGHTLY] TIMEOUT: Exceeded {MAX_RUNTIME}s", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[NIGHTLY] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
