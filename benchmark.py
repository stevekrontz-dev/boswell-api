#!/usr/bin/env python3
"""
Boswell System Benchmark — repeatable health snapshot.

Run periodically to track performance, memory health, and search quality over time.
Results are printed as a report and optionally committed to Boswell for historical tracking.

Usage:
    python benchmark.py                    # Run benchmark, print report
    python benchmark.py --commit           # Run + commit results to Boswell
    python benchmark.py --history          # Show previous benchmark results
    railway run python benchmark.py        # Run against production

Metrics tracked:
    1. Response times: P50, P95, P99, avg (from audit_logs)
    2. Endpoint breakdown: P95 per endpoint
    3. Trail health: state distribution (active/fading/dormant/archived)
    4. Memory tiers: candidates by status, commits by silt_status
    5. Search quality: standard queries, latency, staged vs permanent ratio
    6. Startup weight: token estimate for normal verbosity
    7. Nightly cron: last run, duration, results
"""

import json
import os
import sys
import time
from datetime import datetime

import psycopg2
import psycopg2.extras
import requests

BOSWELL_URL = os.environ.get(
    'BOSWELL_URL',
    'https://delightful-imagination-production-f6a1.up.railway.app'
)
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Standard benchmark queries — same every run for comparability
BENCHMARK_QUERIES = [
    {"query": "selfhood loss thesis", "expect_staged": True},
    {"query": "architectural decisions", "expect_staged": False},
    {"query": "Cortex respiratory architecture", "expect_staged": True},
    {"query": "tint atlanta CRM", "expect_staged": False},
    {"query": "decay freeze sacred directive", "expect_staged": False},
]


def get_db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set. Use 'railway run' or set env var.", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def measure_response_times(cur):
    """P50/P95/P99/avg from audit_logs over last 24 hours."""
    cur.execute("""
        SELECT
            COUNT(*) as total_requests,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms)::numeric, 1) as p50,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric, 1) as p95,
            ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms)::numeric, 1) as p99,
            ROUND(AVG(duration_ms)::numeric, 1) as avg_ms
        FROM audit_logs
        WHERE timestamp > NOW() - INTERVAL '24 hours'
    """)
    return dict(cur.fetchone())


def measure_endpoint_breakdown(cur, top_n=10):
    """P95 per endpoint over last 24 hours."""
    cur.execute("""
        SELECT
            split_part(request_metadata->>'path', '?', 1) as endpoint,
            COUNT(*) as requests,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric, 1) as p95,
            ROUND(AVG(duration_ms)::numeric, 1) as avg_ms
        FROM audit_logs
        WHERE timestamp > NOW() - INTERVAL '24 hours'
        GROUP BY 1
        HAVING COUNT(*) >= 5
        ORDER BY p95 DESC
        LIMIT %s
    """, (top_n,))
    return [dict(r) for r in cur.fetchall()]


def measure_trail_health(cur):
    """Trail state distribution with FSRS-6 metrics."""
    cur.execute("""
        SELECT state,
               COUNT(*) as count,
               ROUND(AVG(COALESCE(retrieval_strength, 1.0))::numeric, 3) as avg_retrieval,
               ROUND(AVG(COALESCE(storage_strength, 1.0))::numeric, 3) as avg_storage,
               ROUND(AVG(COALESCE(stability, 1.0))::numeric, 3) as avg_stability
        FROM trails
        GROUP BY state
        ORDER BY state
    """)
    return {r['state'] or 'unknown': dict(r) for r in cur.fetchall()}


def measure_memory_tiers(cur):
    """Candidate status distribution and commit silt counts."""
    # Candidates
    cur.execute("""
        SELECT status, COUNT(*) as count
        FROM candidate_memories
        GROUP BY status
        ORDER BY status
    """)
    candidates = {r['status']: r['count'] for r in cur.fetchall()}

    # Commits
    cur.execute("SELECT COUNT(*) as total FROM commits")
    total_commits = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) as silted FROM commits WHERE silt_status IS NOT NULL")
    silted_commits = cur.fetchone()['silted']

    # Blobs
    cur.execute("SELECT COUNT(*) as total FROM blobs")
    total_blobs = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) as with_embedding FROM blobs WHERE embedding IS NOT NULL")
    embedded_blobs = cur.fetchone()['with_embedding']

    return {
        'candidates': candidates,
        'commits': {'total': total_commits, 'silted': silted_commits, 'active': total_commits - silted_commits},
        'blobs': {'total': total_blobs, 'with_embedding': embedded_blobs},
    }


def measure_search_quality():
    """Run standard queries against the API and measure latency + result quality."""
    results = []
    for bq in BENCHMARK_QUERIES:
        start = time.time()
        try:
            resp = requests.get(
                f"{BOSWELL_URL}/v2/search",
                params={"q": bq['query'], "limit": 10, "mode": "hybrid"},
                timeout=10,
            )
            elapsed_ms = int((time.time() - start) * 1000)
            data = resp.json()

            search_results = data.get('results', [])
            staged_count = sum(1 for r in search_results if r.get('source') == 'staged')
            permanent_count = sum(1 for r in search_results if r.get('source') == 'permanent')
            total = len(search_results)

            results.append({
                'query': bq['query'],
                'latency_ms': elapsed_ms,
                'total_results': total,
                'staged': staged_count,
                'permanent': permanent_count,
                'staged_found': staged_count > 0,
                'expected_staged': bq['expect_staged'],
                'quality_pass': (staged_count > 0) == bq['expect_staged'] if bq['expect_staged'] else True,
            })
        except Exception as e:
            results.append({
                'query': bq['query'],
                'error': str(e),
                'quality_pass': False,
            })

    return results


def measure_nightly_status(cur):
    """Check last nightly cron execution."""
    try:
        cur.execute("""
            SELECT timestamp, duration_ms,
                   request_metadata->>'path' as path
            FROM audit_logs
            WHERE action = 'POST_UNKNOWN'
              AND request_metadata->>'path' LIKE '/v2/nightly%'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return {
                'last_run': str(row['timestamp']),
                'duration_ms': row['duration_ms'],
                'status': 'active',
            }
    except Exception:
        pass

    return {'status': 'unknown', 'last_run': None}


def measure_immune_status(cur):
    """Check last immune patrol."""
    try:
        cur.execute("""
            SELECT timestamp, duration_ms
            FROM audit_logs
            WHERE request_metadata->>'path' LIKE '/v2/immune/patrol%'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return {
                'last_patrol': str(row['timestamp']),
                'duration_ms': row['duration_ms'],
            }
    except Exception:
        pass
    return {'last_patrol': None}


def run_benchmark():
    """Execute full benchmark suite."""
    print("=" * 60)
    print(f"  BOSWELL SYSTEM BENCHMARK — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    db = get_db()
    cur = db.cursor()

    report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'version': '1.0',
    }

    # 1. Response times
    print("\n[1/6] Response Times (24h)...")
    rt = measure_response_times(cur)
    report['response_times'] = rt
    p95_status = "PASS" if (rt['p95'] or 0) < 500 else "FAIL"
    print(f"  P50: {rt['p50']}ms | P95: {rt['p95']}ms [{p95_status}] | P99: {rt['p99']}ms | Avg: {rt['avg_ms']}ms")
    print(f"  Total requests: {rt['total_requests']}")

    # 2. Endpoint breakdown
    print("\n[2/6] Slowest Endpoints (P95)...")
    endpoints = measure_endpoint_breakdown(cur)
    report['endpoints'] = endpoints
    for ep in endpoints[:5]:
        flag = " <<<" if (ep['p95'] or 0) > 500 else ""
        print(f"  {ep['endpoint']:40s} P95={ep['p95']}ms  ({ep['requests']} reqs){flag}")

    # 3. Trail health
    print("\n[3/6] Trail Health...")
    trails = measure_trail_health(cur)
    report['trails'] = trails
    for state, data in trails.items():
        print(f"  {state:12s}: {data['count']:5d}  (R={data['avg_retrieval']}, S={data['avg_storage']}, stab={data['avg_stability']})")

    # 4. Memory tiers
    print("\n[4/6] Memory Tiers...")
    tiers = measure_memory_tiers(cur)
    report['memory_tiers'] = tiers
    print(f"  Commits: {tiers['commits']['total']} total, {tiers['commits']['silted']} silted")
    print(f"  Blobs: {tiers['blobs']['total']} total, {tiers['blobs']['with_embedding']} with embedding")
    print(f"  Candidates: {tiers['candidates']}")

    # 5. Search quality
    print("\n[5/6] Search Quality...")
    search = measure_search_quality()
    report['search_quality'] = search
    passes = sum(1 for s in search if s.get('quality_pass', False))
    for s in search:
        if 'error' in s:
            print(f"  {s['query']:40s} ERROR: {s['error']}")
        else:
            status = "PASS" if s['quality_pass'] else "FAIL"
            print(f"  {s['query']:40s} {s['latency_ms']:4d}ms  {s['staged']}staged/{s['permanent']}perm  [{status}]")
    print(f"  Quality: {passes}/{len(search)} passed")

    # 6. Cron status
    print("\n[6/6] Cron Status...")
    nightly = measure_nightly_status(cur)
    immune = measure_immune_status(cur)
    report['cron'] = {'nightly': nightly, 'immune': immune}
    print(f"  Nightly: {nightly.get('status', 'unknown')} (last: {nightly.get('last_run', 'never')})")
    print(f"  Immune:  last patrol {immune.get('last_patrol', 'never')}")

    cur.close()
    db.close()

    # Summary
    print("\n" + "=" * 60)
    p95_val = rt['p95'] or 0
    search_pass_rate = passes / len(search) if search else 0
    dormant_count = trails.get('dormant', {}).get('count', 0)
    archived_count = trails.get('archived', {}).get('count', 0)

    grade = "A" if p95_val < 300 and search_pass_rate == 1.0 else \
            "B" if p95_val < 500 and search_pass_rate >= 0.8 else \
            "C" if p95_val < 1000 else \
            "D" if p95_val < 2000 else "F"

    report['grade'] = grade
    report['summary'] = {
        'p95_ms': float(p95_val),
        'p95_pass': p95_val < 500,
        'search_pass_rate': search_pass_rate,
        'dormant_trails': dormant_count,
        'archived_trails': archived_count,
        'silted_commits': tiers['commits']['silted'],
        'total_candidates': sum(tiers['candidates'].values()),
    }

    print(f"  GRADE: {grade}")
    print(f"  P95: {p95_val}ms ({'PASS' if p95_val < 500 else 'FAIL'})")
    print(f"  Search: {passes}/{len(search)} queries pass")
    print(f"  Decay: {dormant_count} dormant, {archived_count} archived trails")
    print(f"  Silt: {tiers['commits']['silted']} commits silted")
    print("=" * 60)

    return report


def commit_to_boswell(report):
    """Commit benchmark results to Boswell for historical tracking."""
    try:
        resp = requests.post(
            f"{BOSWELL_URL}/v2/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "boswell_bookmark",
                    "arguments": {
                        "branch": "boswell",
                        "summary": f"BENCHMARK {report['timestamp'][:10]}: Grade {report['grade']}, P95={report['summary']['p95_ms']}ms, Search {report['summary']['search_pass_rate']:.0%}",
                        "content": report,
                        "salience": 0.3,
                        "tags": ["benchmark", "automated"],
                    }
                }
            },
            timeout=10,
        )
        if resp.status_code == 200:
            print("\nBenchmark committed to Boswell.")
        else:
            print(f"\nFailed to commit to Boswell: {resp.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"\nFailed to commit to Boswell: {e}", file=sys.stderr)


if __name__ == '__main__':
    report = run_benchmark()

    if '--commit' in sys.argv:
        commit_to_boswell(report)

    if '--json' in sys.argv:
        print(json.dumps(report, indent=2, default=str))
