#!/usr/bin/env python3
"""
boswell_scheduler — APScheduler shell for in-process platform-internal jobs.

Replaces the cron→HTTP→PUBLIC_PATHS→DEFAULT_TENANT-fallback loop that
silently starved non-DEFAULT tenants of embedding work. The HTTP boundary
is what made the bug expressible; collapsing scheduled work into
in-process function calls removes the boundary and the fallback surface.

Two decorators:

    @scheduled(cron='*/5 * * * *', subscription='embedding',
               heartbeat_key='embedding_backfill')
    def backfill_embeddings_for_tenant(tenant):
        # called once per subscribed tenant per cron fire; tenant override
        # is already pushed.
        ...

    @scheduled_global(cron='*/30 * * * *', heartbeat_key='alert_check')
    def dispatch_alerts():
        # called once per cron fire (no tenant iteration).
        ...

Coordination across gunicorn workers (and any additional Railway replicas
sharing the database) uses a Postgres session-level advisory lock. The
first worker to acquire the lock starts the scheduler; the rest stay
passive. If the lock-holder dies, its connection drops and the lock
releases — the next worker to start (or the next deploy) re-acquires.
This is good-enough for the current single-replica web service and stays
correct if we scale horizontally.
"""

import os
import sys
import time
import threading

import psycopg2

# Arbitrary 64-bit constant. Picked once and never changed; if you need a
# second independent lock, pick a different constant — don't reuse this.
_SCHEDULER_LOCK_KEY = 0x80511E11

_scheduled_jobs = []          # per-tenant jobs registered via @scheduled
_scheduled_global_jobs = []   # single-shot jobs via @scheduled_global

_started = False
_lock_conn = None             # session-level advisory-lock connection (kept open)


def scheduled(cron, subscription, heartbeat_key=None,
              expected_interval_minutes=5):
    """Decorator: register a per-tenant scheduled job.

    cron: standard 5-field crontab string (e.g. '*/5 * * * *')
    subscription: key in tenants.subscriptions JSONB (e.g. 'embedding')
    heartbeat_key: cron_heartbeats.service value; defaults to subscription
    expected_interval_minutes: written to the heartbeat row for Alert 6
    """

    def decorator(fn):
        _scheduled_jobs.append({
            'fn': fn,
            'cron': cron,
            'subscription': subscription,
            'heartbeat_key': heartbeat_key or subscription,
            'expected_interval_minutes': expected_interval_minutes,
            'name': fn.__name__,
        })
        return fn

    return decorator


def scheduled_global(cron, heartbeat_key, expected_interval_minutes=30):
    """Decorator: register a single-shot scheduled job (no tenant iteration).

    For platform-internal work like dispatch_alerts that has no per-tenant
    body. Sibling to @scheduled.
    """

    def decorator(fn):
        _scheduled_global_jobs.append({
            'fn': fn,
            'cron': cron,
            'heartbeat_key': heartbeat_key,
            'expected_interval_minutes': expected_interval_minutes,
            'name': fn.__name__,
        })
        return fn

    return decorator


def _try_acquire_lock(database_url):
    """Try to acquire a session-level pg_advisory_lock. Returns the
    connection on success (must be kept open for lock to hold) or None."""
    try:
        conn = psycopg2.connect(database_url, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_SCHEDULER_LOCK_KEY,))
        got = cur.fetchone()[0]
        cur.close()
        if got:
            return conn
        conn.close()
        return None
    except Exception as e:
        print(f"[SCHEDULER] advisory lock acquire failed: {e}", file=sys.stderr)
        return None


def _make_per_tenant_runner(app, job, helpers):
    """Build the APScheduler-callable runner for an @scheduled job.

    Iterates subscribed tenants, push/pops tenant override around the
    body, aggregates work counts, writes ONE heartbeat per cron fire.
    """
    fn = job['fn']
    subscription = job['subscription']
    heartbeat_key = job['heartbeat_key']
    expected = job['expected_interval_minutes']

    get_subscribed_tenants = helpers['get_subscribed_tenants']
    push_tenant_override = helpers['push_tenant_override']
    pop_tenant_override = helpers['pop_tenant_override']
    write_heartbeat = helpers['write_heartbeat']

    def runner():
        start = time.time()
        total_work = 0
        errors = 0
        processed = []
        tenants = []

        try:
            with app.test_request_context():
                tenants = get_subscribed_tenants(subscription)
        except Exception as e:
            print(f"[SCHEDULER] {heartbeat_key}: tenant fetch failed: {e}",
                  file=sys.stderr)
            try:
                with app.test_request_context():
                    write_heartbeat(
                        heartbeat_key, 'error',
                        f"tenant fetch failed: {str(e)[:200]}",
                        work_done=0,
                        expected_interval_minutes=expected,
                    )
            except Exception:
                pass
            return

        for t in tenants:
            push_tenant_override(t.id)
            try:
                with app.test_request_context():
                    result = fn(t)
                work = 0
                if isinstance(result, dict):
                    work = (result.get('blobs', 0)
                            + result.get('candidates', 0)
                            + result.get('work', 0))
                elif isinstance(result, int):
                    work = result
                total_work += work
                processed.append({'id': t.id[:8], 'work': work})
            except Exception as e:
                errors += 1
                print(f"[SCHEDULER] {heartbeat_key} tenant {t.id[:8]} "
                      f"failed: {e}", file=sys.stderr)
            finally:
                pop_tenant_override()

        duration_ms = int((time.time() - start) * 1000)
        if errors > 0 and total_work == 0:
            status = 'error'
        elif total_work > 0:
            status = 'ok'
        else:
            status = 'no_work'

        msg = (f"tenants={len(tenants)} work={total_work} "
               f"errors={errors} duration_ms={duration_ms}")
        try:
            with app.test_request_context():
                write_heartbeat(
                    heartbeat_key, status, msg,
                    work_done=total_work,
                    expected_interval_minutes=expected,
                )
        except Exception as e:
            print(f"[SCHEDULER] {heartbeat_key}: heartbeat write failed: {e}",
                  file=sys.stderr)

        print(f"[SCHEDULER] {heartbeat_key}: {msg}", file=sys.stderr)

    return runner


def _make_global_runner(app, job, helpers):
    """Build the APScheduler-callable runner for a @scheduled_global job."""
    fn = job['fn']
    heartbeat_key = job['heartbeat_key']
    expected = job['expected_interval_minutes']
    write_heartbeat = helpers['write_heartbeat']

    def runner():
        start = time.time()
        try:
            with app.test_request_context():
                result = fn()
            work = result if isinstance(result, int) else 0
            duration_ms = int((time.time() - start) * 1000)
            status = 'ok' if work > 0 else 'no_work'
            msg = f"work={work} duration_ms={duration_ms}"
            with app.test_request_context():
                write_heartbeat(
                    heartbeat_key, status, msg,
                    work_done=work,
                    expected_interval_minutes=expected,
                )
            print(f"[SCHEDULER] {heartbeat_key}: {msg}", file=sys.stderr)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            print(f"[SCHEDULER] {heartbeat_key} failed: {e}", file=sys.stderr)
            try:
                with app.test_request_context():
                    write_heartbeat(
                        heartbeat_key, 'error',
                        f"{str(e)[:200]} duration_ms={duration_ms}",
                        work_done=0,
                        expected_interval_minutes=expected,
                    )
            except Exception:
                pass

    return runner


def start_scheduler(app, helpers, database_url=None, enabled=True):
    """Start the in-process scheduler if this process wins the advisory lock.

    helpers: dict with keys 'get_subscribed_tenants', 'push_tenant_override',
        'pop_tenant_override', 'write_heartbeat'. Passed in to avoid a
        circular import with app.py.

    Idempotent: safe to call multiple times. Only the first lock-winning
    call starts a real scheduler; subsequent calls are no-ops.
    """
    global _started, _lock_conn

    if not enabled:
        print("[SCHEDULER] disabled via flag, skipping", file=sys.stderr)
        return False

    if _started:
        return True

    database_url = database_url or os.environ.get('DATABASE_URL')
    if not database_url:
        print("[SCHEDULER] DATABASE_URL not set, skipping", file=sys.stderr)
        return False

    if not _scheduled_jobs and not _scheduled_global_jobs:
        print("[SCHEDULER] no jobs registered, skipping", file=sys.stderr)
        return False

    conn = _try_acquire_lock(database_url)
    if conn is None:
        print("[SCHEDULER] another process holds the lock, staying passive",
              file=sys.stderr)
        return False

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except Exception as e:
        print(f"[SCHEDULER] APScheduler import failed: {e}", file=sys.stderr)
        try:
            conn.close()
        except Exception:
            pass
        return False

    _lock_conn = conn

    sched = BackgroundScheduler(
        timezone='UTC',
        job_defaults={
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 60,
        },
    )

    for job in _scheduled_jobs:
        runner = _make_per_tenant_runner(app, job, helpers)
        sched.add_job(
            runner,
            CronTrigger.from_crontab(job['cron'], timezone='UTC'),
            id=f"per_tenant::{job['heartbeat_key']}",
            name=job['name'],
            replace_existing=True,
        )
        print(f"[SCHEDULER] {job['name']} scheduled {job['cron']} "
              f"(subscription='{job['subscription']}', "
              f"heartbeat='{job['heartbeat_key']}')", file=sys.stderr)

    for job in _scheduled_global_jobs:
        runner = _make_global_runner(app, job, helpers)
        sched.add_job(
            runner,
            CronTrigger.from_crontab(job['cron'], timezone='UTC'),
            id=f"global::{job['heartbeat_key']}",
            name=job['name'],
            replace_existing=True,
        )
        print(f"[SCHEDULER] {job['name']} scheduled {job['cron']} "
              f"(global, heartbeat='{job['heartbeat_key']}')",
              file=sys.stderr)

    sched.start()
    _started = True
    print(f"[SCHEDULER] started with {len(_scheduled_jobs)} per-tenant + "
          f"{len(_scheduled_global_jobs)} global jobs", file=sys.stderr)

    # Best-effort heartbeat refresh on the lock connection so a long-idle
    # connection doesn't get reaped by Postgres / pgbouncer / Railway.
    def _keepalive():
        while _started:
            time.sleep(60)
            try:
                cur = _lock_conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
            except Exception as e:
                print(f"[SCHEDULER] keepalive failed: {e}", file=sys.stderr)
                return

    threading.Thread(target=_keepalive, daemon=True, name='aps-keepalive').start()
    return True
