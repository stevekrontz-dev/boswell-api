#!/usr/bin/env python3
"""
Immune system patrol cron worker.
Run via Railway cron or external scheduler.
Cadence: Daily at 3am UTC
Budget: 5 minute max runtime
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
    """Run immune system patrol."""
    url = f"{BOSWELL_URL}/v2/immune/patrol"

    print(f"[IMMUNE] Starting patrol at {url}")

    try:
        response = requests.post(
            url,
            json={"auto_quarantine": True},
            timeout=MAX_RUNTIME
        )
        data = response.json()

        patrol_id = data.get('patrol_id', 'unknown')
        routes_checked = len(data.get('routes_checked', []))
        findings = len(data.get('findings', []))
        quarantined = len(data.get('quarantined', []))
        errors = data.get('errors', [])
        duration = data.get('duration_seconds', 0)

        print(f"[IMMUNE] Patrol {patrol_id} complete")
        print(f"[IMMUNE] Routes checked: {routes_checked}")
        print(f"[IMMUNE] Findings: {findings}")
        print(f"[IMMUNE] Quarantined: {quarantined}")
        print(f"[IMMUNE] Duration: {duration}s")

        if errors:
            print(f"[IMMUNE] Errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)

        # Classify errors. A few routes have *known* recurring failures that
        # the patrol endpoint handles gracefully (isolated via transaction
        # rollback; the other routes run to completion). We don't want those
        # to fail the cron run because Railway reads exit code as health and
        # a red dot here obscures real incidents.
        #
        # Known-isolated:
        #   CONTRADICTION — 60s statement_timeout on the n² pairwise-blob
        #   JOIN (app.py:8686). Tracked for optimization in T4. Not an
        #   operational failure.
        KNOWN_ISOLATED_ROUTES = {'CONTRADICTION'}
        unexpected_errors = [e for e in errors if e.get('route') not in KNOWN_ISOLATED_ROUTES]

        if unexpected_errors:
            print(f"[IMMUNE] {len(unexpected_errors)} unexpected error(s) — exit 1", file=sys.stderr)
            sys.exit(1)

        if errors:
            # All errors were known-isolated. Log but don't fail the run.
            print(f"[IMMUNE] All {len(errors)} error(s) are known-isolated; exit 0")

        # Exit with warning if quarantined items need review
        if quarantined > 0:
            print(f"[IMMUNE] WARNING: {quarantined} memories quarantined - review needed", file=sys.stderr)

        sys.exit(0)

    except requests.Timeout:
        print(f"[IMMUNE] TIMEOUT: Patrol exceeded {MAX_RUNTIME}s", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[IMMUNE] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
