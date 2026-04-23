#!/usr/bin/env python3
"""
Consolidation bridge cron worker (Boswell v4.0).
Run via Railway cron service.
Cadence: Every 6 hours (0 */6 * * *)
Budget: 5 minute max runtime

Bridges the promotion-path gap between c49cb56's nightly consolidation disable
(2026-04-07) and the eventual Curator Stack. Iterates all tenants, runs
cycle_type='manual' consolidation with a conservative max_promotions+min_score,
writes a cron_heartbeats row so future silent failures are visible.

Sacred rule: every scheduled consolidation-layer service writes a heartbeat.
See boswell commit e612899e for the operational commitment.
"""

import os
import sys
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)

# Max runtime in seconds (5 minutes, matches nightly_cron pattern)
MAX_RUNTIME = 300


def main():
    """Run one consolidation bridge cycle across all tenants."""
    url = f"{BOSWELL_URL}/v2/consolidate_all_tenants"

    print(f"[CONSOLIDATION_BRIDGE] Starting at {url}")

    try:
        response = requests.post(
            url,
            json={},
            timeout=MAX_RUNTIME,
        )
        data = response.json()

        status = data.get('status', 'unknown')
        duration = data.get('duration_ms', 0)
        tenants = data.get('tenants_processed', 0)
        failed = data.get('tenants_failed', 0)
        total_promoted = data.get('total_promoted', 0)

        print(f"[CONSOLIDATION_BRIDGE] {status} in {duration}ms")
        print(
            f"[CONSOLIDATION_BRIDGE] tenants={tenants} failed={failed} "
            f"total_promoted={total_promoted}"
        )

        if failed > 0:
            print(
                f"[CONSOLIDATION_BRIDGE] Failed tenants: {data.get('failed', [])}",
                file=sys.stderr,
            )
            sys.exit(1)

        sys.exit(0)

    except requests.Timeout:
        print(f"[CONSOLIDATION_BRIDGE] TIMEOUT: Exceeded {MAX_RUNTIME}s", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[CONSOLIDATION_BRIDGE] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
