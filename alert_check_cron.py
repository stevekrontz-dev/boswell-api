#!/usr/bin/env python3
"""
Alert-check cron worker (Boswell v4.0).
Run via Railway cron service.
Cadence: Every 30 minutes (*/30 * * * *)
Budget: 60 second max runtime

POSTs to /v2/health/alert-check which: polls admin_alerts for critical alerts,
deduplicates by alert_key, throttles email notifications per-key, sends via Resend
to ALERT_EMAIL_TO (default: stevekrontz@gmail.com).

Heartbeat 'alert_check' written inside the endpoint handler; expected_interval=30.

The endpoint requires either INTERNAL_SECRET header OR admin JWT. This script
uses INTERNAL_SECRET (cron scripts can't hold JWTs) — see auth/__init__.py
is_internal_request() and app.py:929-950.

Background: before this cron existed, admin_alerts was computing critical alerts
that nothing dispatched. Alert 6 + Alert 7 were firing but never emailed Steve.
See ops-postmortems d0c4ae95 THIRD SURFACING addendum for the recursive-
observability history.
"""

import os
import sys
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)

INTERNAL_SECRET = os.environ.get('INTERNAL_SECRET')

MAX_RUNTIME = 60


def main():
    if not INTERNAL_SECRET:
        print("[ALERT-CHECK] FATAL: INTERNAL_SECRET env var not set", file=sys.stderr)
        sys.exit(1)

    url = f"{BOSWELL_URL}/v2/health/alert-check"
    print(f"[ALERT-CHECK] Starting at {url}")

    try:
        response = requests.post(
            url,
            headers={'X-Boswell-Internal': INTERNAL_SECRET},
            json={},
            timeout=MAX_RUNTIME,
        )
        response.raise_for_status()
        data = response.json()

        critical = data.get('critical_count', 0)
        notified = data.get('notified_count', 0)
        resolved = data.get('resolved_count', 0)
        throttle_hours = data.get('throttle_hours', 0)

        print(
            f"[ALERT-CHECK] critical={critical} notified={notified} "
            f"resolved={resolved} throttle_hours={throttle_hours}"
        )
        sys.exit(0)

    except requests.Timeout:
        print(f"[ALERT-CHECK] TIMEOUT: Exceeded {MAX_RUNTIME}s", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ALERT-CHECK] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
