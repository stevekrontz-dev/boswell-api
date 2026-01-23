#!/usr/bin/env python3
"""
Health daemon cron worker.
Run via Railway cron or external scheduler.
"""

import os
import sys
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)

def main():
    """Ping health daemon endpoint."""
    url = f"{BOSWELL_URL}/v2/health/daemon"
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        status = data.get('status', 'unknown')
        checks_passed = data.get('summary', {}).get('checks_passed', 0)
        checks_total = data.get('summary', {}).get('checks_total', 0)

        print(f"[HEALTH] {status.upper()} - {checks_passed}/{checks_total} checks passed")

        if status == 'unhealthy':
            print(f"[HEALTH] ALERT: System unhealthy!", file=sys.stderr)
            sys.exit(1)

        sys.exit(0)
    except Exception as e:
        print(f"[HEALTH] FAILED: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
