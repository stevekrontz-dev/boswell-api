#!/usr/bin/env python3
"""
Health daemon cron worker.
Run via Railway cron or external scheduler.

Exit semantics:
  - Exit 0: the cron successfully pinged /v2/health/daemon. System health
    (unhealthy/degraded/healthy) is the daemon's concern, not the cron's.
    Paging on critical alerts is alert_check's job — NOT Railway's CRASHED
    notification. Conflating "system unhealthy" with "cron broken" produced
    the 2026-04-24 crash-email storm (45+ notifications in 8h).
  - Exit 1: the cron could not reach the daemon after MAX_RETRIES attempts.
    That IS a real cron failure worth paging on.

Retries absorb Railway's rolling-deploy 503 window (~30s during container
swap). Without retry, a cron fire caught mid-rollout crashes the cron.
"""

import os
import sys
import time
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)

MAX_RETRIES = 3
BACKOFF_BASE_S = 2  # 2s, 4s


def main():
    """Ping health daemon endpoint with bounded retry on transient failures."""
    url = f"{BOSWELL_URL}/v2/health/daemon"
    last_err = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=30)
            # The daemon at /v2/health/daemon deliberately returns HTTP 503
            # when overall_status='unhealthy' (app.py:884). That is NOT a
            # transport failure — it's the daemon successfully reporting bad
            # news. raise_for_status() would treat 503 as transient and
            # retry-then-exit-1, conflating "system unhealthy" with "cron
            # broken." Don't raise on 503 if the body is parseable health
            # JSON; treat it as a successful ping per docstring.
            try:
                data = response.json()
            except ValueError:
                # Body isn't JSON — that's a real protocol failure (proxy
                # error page, container swap mid-rollout, etc). Retry.
                response.raise_for_status()
                # If status was 2xx but body unparseable, raise our own error
                raise requests.HTTPError(
                    f"non-JSON response from daemon (status={response.status_code})"
                )

            status = data.get('status', 'unknown')
            summary = data.get('summary', {})
            checks_passed = summary.get('checks_passed', 0)
            checks_total = summary.get('checks_total', 0)
            alerts_critical = summary.get('alerts_critical', 0)

            print(
                f"[HEALTH] {status.upper()} - {checks_passed}/{checks_total} "
                f"checks passed, alerts_critical={alerts_critical} "
                f"http={response.status_code}"
            )

            if status == 'unhealthy':
                # Log loudly but exit 0: paging happens via admin_alerts +
                # alert_check emails, not Railway CRASHED notifications.
                print(
                    f"[HEALTH] system reports unhealthy "
                    f"(alerts_critical={alerts_critical}) — "
                    f"alert_check handles paging",
                    file=sys.stderr
                )

            sys.exit(0)

        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_S * (2 ** (attempt - 1))
                print(
                    f"[HEALTH] attempt {attempt}/{MAX_RETRIES} failed ({e}); "
                    f"retrying in {delay}s",
                    file=sys.stderr
                )
                time.sleep(delay)
            else:
                print(
                    f"[HEALTH] FAILED after {MAX_RETRIES} attempts: {last_err}",
                    file=sys.stderr
                )
                sys.exit(1)


if __name__ == '__main__':
    main()
