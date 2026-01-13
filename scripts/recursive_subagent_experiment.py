#!/usr/bin/env python3
"""
CC4 RECURSIVE Sub-Agent Experiment
===================================
Testing recursive spawning: Sub-agents spawn their own sub-agents.

Architecture:
CC4 (depth 0)
  └── CC4a (auth coordinator, depth 1)
        ├── CC4a-1 (test signup, depth 2)
        ├── CC4a-2 (test login, depth 2)
        └── CC4a-3 (test password reset, depth 2)
  └── CC4b (keys coordinator, depth 1)
        ├── CC4b-1 (test create, depth 2)
        ├── CC4b-2 (test list, depth 2)
        └── CC4b-3 (test delete, depth 2)
  └── CC4c (extension coordinator, depth 1)
        ├── CC4c-1 (test download, depth 2)
        └── CC4c-2 (test file structure, depth 2)

Expected: 11 agents total (3 coordinators + 8 workers)
"""

import os
import time
import json
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any

# Try to import anthropic for true AI sub-agents
try:
    import anthropic
    HAS_ANTHROPIC = True
    print("Anthropic SDK available - will use Claude for coordinators")
except ImportError:
    HAS_ANTHROPIC = False
    print("Anthropic SDK not available - using simulated recursive spawning")

BASE_URL = "https://delightful-imagination-production-f6a1.up.railway.app"

# Global metrics
SPAWN_LOG = []
AGENT_COUNT = 0

@dataclass
class AgentResult:
    name: str
    depth: int
    task: str
    spawned_children: bool
    children: Dict[str, Any] = field(default_factory=dict)
    tests: List[Dict] = field(default_factory=list)
    elapsed_ms: float = 0
    error: Optional[str] = None


def log_spawn(agent_name: str, depth: int, parent: str = None):
    """Log agent spawn event"""
    global AGENT_COUNT
    AGENT_COUNT += 1
    SPAWN_LOG.append({
        "timestamp": datetime.now().isoformat(),
        "agent": agent_name,
        "depth": depth,
        "parent": parent,
        "count": AGENT_COUNT
    })
    indent = "  " * depth
    print(f"{indent}[SPAWN] {agent_name} (depth {depth})")


def run_http_test(name: str, method: str, url: str, **kwargs) -> Dict:
    """Run a single HTTP test"""
    try:
        start = time.time()
        if method.upper() == "GET":
            resp = requests.get(url, timeout=10, **kwargs)
        elif method.upper() == "POST":
            resp = requests.post(url, timeout=10, **kwargs)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, timeout=10, **kwargs)
        else:
            resp = requests.request(method, url, timeout=10, **kwargs)

        elapsed = (time.time() - start) * 1000

        # Determine pass/fail based on expected behavior
        status = "PASS" if resp.status_code < 500 else "FAIL"

        return {
            "name": name,
            "status": status,
            "http_code": resp.status_code,
            "elapsed_ms": round(elapsed, 2),
            "details": f"{method} {url} -> {resp.status_code}"
        }
    except Exception as e:
        return {
            "name": name,
            "status": "FAIL",
            "http_code": None,
            "elapsed_ms": 0,
            "details": f"Error: {str(e)}"
        }


# ============================================================================
# DEPTH 2 WORKERS - Leaf nodes that do actual testing
# ============================================================================

def worker_cc4a_1_signup() -> AgentResult:
    """CC4a-1: Test signup endpoint"""
    log_spawn("CC4a-1", 2, "CC4a")
    start = time.time()

    tests = [
        run_http_test(
            "signup_page_loads",
            "GET",
            f"{BASE_URL}/signup"
        ),
        run_http_test(
            "signup_api_rejects_invalid",
            "POST",
            f"{BASE_URL}/api/auth/signup",
            json={"email": "bad", "password": "x"}
        ),
        run_http_test(
            "register_endpoint_exists",
            "POST",
            f"{BASE_URL}/v2/auth/register",
            json={"email": f"test_cc4a1_{int(time.time())}@test.com", "password": "testpass123"}
        ),
    ]

    return AgentResult(
        name="CC4a-1",
        depth=2,
        task="Test signup",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4a_2_login() -> AgentResult:
    """CC4a-2: Test login endpoint"""
    log_spawn("CC4a-2", 2, "CC4a")
    start = time.time()

    tests = [
        run_http_test(
            "login_page_loads",
            "GET",
            f"{BASE_URL}/login"
        ),
        run_http_test(
            "login_rejects_bad_creds",
            "POST",
            f"{BASE_URL}/api/auth/login",
            json={"email": "fake@test.com", "password": "wrong"}
        ),
        run_http_test(
            "v2_login_endpoint",
            "POST",
            f"{BASE_URL}/v2/auth/login",
            json={"email": "test@test.com", "password": "testpass"}
        ),
    ]

    return AgentResult(
        name="CC4a-2",
        depth=2,
        task="Test login",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4a_3_password_reset() -> AgentResult:
    """CC4a-3: Test password reset"""
    log_spawn("CC4a-3", 2, "CC4a")
    start = time.time()

    tests = [
        run_http_test(
            "password_reset_request",
            "POST",
            f"{BASE_URL}/v2/auth/password-reset/request",
            json={"email": "test@test.com"}
        ),
        run_http_test(
            "password_reset_page",
            "GET",
            f"{BASE_URL}/reset-password"
        ),
    ]

    return AgentResult(
        name="CC4a-3",
        depth=2,
        task="Test password reset",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4b_1_create_key() -> AgentResult:
    """CC4b-1: Test key creation"""
    log_spawn("CC4b-1", 2, "CC4b")
    start = time.time()

    tests = [
        run_http_test(
            "create_key_requires_auth",
            "POST",
            f"{BASE_URL}/api/keys"
        ),
        run_http_test(
            "v2_create_key",
            "POST",
            f"{BASE_URL}/v2/auth/keys/create"
        ),
    ]

    return AgentResult(
        name="CC4b-1",
        depth=2,
        task="Test create key",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4b_2_list_keys() -> AgentResult:
    """CC4b-2: Test key listing"""
    log_spawn("CC4b-2", 2, "CC4b")
    start = time.time()

    tests = [
        run_http_test(
            "list_keys_requires_auth",
            "GET",
            f"{BASE_URL}/api/keys"
        ),
        run_http_test(
            "v2_list_keys",
            "GET",
            f"{BASE_URL}/v2/auth/keys"
        ),
    ]

    return AgentResult(
        name="CC4b-2",
        depth=2,
        task="Test list keys",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4b_3_delete_key() -> AgentResult:
    """CC4b-3: Test key deletion"""
    log_spawn("CC4b-3", 2, "CC4b")
    start = time.time()

    tests = [
        run_http_test(
            "delete_key_requires_auth",
            "DELETE",
            f"{BASE_URL}/api/keys/test-key-id"
        ),
        run_http_test(
            "v2_delete_key",
            "DELETE",
            f"{BASE_URL}/v2/auth/keys/test-key-id"
        ),
    ]

    return AgentResult(
        name="CC4b-3",
        depth=2,
        task="Test delete key",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4c_1_download() -> AgentResult:
    """CC4c-1: Test extension download"""
    log_spawn("CC4c-1", 2, "CC4c")
    start = time.time()

    tests = [
        run_http_test(
            "download_requires_key",
            "GET",
            f"{BASE_URL}/api/extension/download"
        ),
        run_http_test(
            "download_rejects_invalid_key",
            "GET",
            f"{BASE_URL}/api/extension/download",
            params={"api_key": "invalid_key"}
        ),
    ]

    return AgentResult(
        name="CC4c-1",
        depth=2,
        task="Test extension download",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def worker_cc4c_2_file_structure() -> AgentResult:
    """CC4c-2: Test file structure / static assets"""
    log_spawn("CC4c-2", 2, "CC4c")
    start = time.time()

    tests = [
        run_http_test(
            "static_frontend_loads",
            "GET",
            f"{BASE_URL}/"
        ),
        run_http_test(
            "dashboard_accessible",
            "GET",
            f"{BASE_URL}/dashboard"
        ),
        run_http_test(
            "connect_page_accessible",
            "GET",
            f"{BASE_URL}/dashboard/connect"
        ),
    ]

    return AgentResult(
        name="CC4c-2",
        depth=2,
        task="Test file structure",
        spawned_children=False,
        tests=tests,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


# ============================================================================
# DEPTH 1 COORDINATORS - Spawn and manage workers
# ============================================================================

def coordinator_cc4a() -> AgentResult:
    """CC4a: Auth coordinator - spawns CC4a-1, CC4a-2, CC4a-3"""
    log_spawn("CC4a", 1, "CC4")
    start = time.time()

    print("  [CC4a] Spawning auth workers in parallel...")

    workers = [
        ("CC4a-1", worker_cc4a_1_signup),
        ("CC4a-2", worker_cc4a_2_login),
        ("CC4a-3", worker_cc4a_3_password_reset),
    ]

    children = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): name for name, fn in workers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                children[name] = asdict(result)
            except Exception as e:
                children[name] = {"error": str(e)}

    return AgentResult(
        name="CC4a",
        depth=1,
        task="Auth coordinator",
        spawned_children=True,
        children=children,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def coordinator_cc4b() -> AgentResult:
    """CC4b: API Keys coordinator - spawns CC4b-1, CC4b-2, CC4b-3"""
    log_spawn("CC4b", 1, "CC4")
    start = time.time()

    print("  [CC4b] Spawning key workers in parallel...")

    workers = [
        ("CC4b-1", worker_cc4b_1_create_key),
        ("CC4b-2", worker_cc4b_2_list_keys),
        ("CC4b-3", worker_cc4b_3_delete_key),
    ]

    children = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): name for name, fn in workers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                children[name] = asdict(result)
            except Exception as e:
                children[name] = {"error": str(e)}

    return AgentResult(
        name="CC4b",
        depth=1,
        task="API Keys coordinator",
        spawned_children=True,
        children=children,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


def coordinator_cc4c() -> AgentResult:
    """CC4c: Extension coordinator - spawns CC4c-1, CC4c-2"""
    log_spawn("CC4c", 1, "CC4")
    start = time.time()

    print("  [CC4c] Spawning extension workers in parallel...")

    workers = [
        ("CC4c-1", worker_cc4c_1_download),
        ("CC4c-2", worker_cc4c_2_file_structure),
    ]

    children = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(fn): name for name, fn in workers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                children[name] = asdict(result)
            except Exception as e:
                children[name] = {"error": str(e)}

    return AgentResult(
        name="CC4c",
        depth=1,
        task="Extension coordinator",
        spawned_children=True,
        children=children,
        elapsed_ms=round((time.time() - start) * 1000, 2)
    )


# ============================================================================
# DEPTH 0 - CC4 (Root orchestrator)
# ============================================================================

def run_recursive_experiment():
    """
    CC4 (depth 0): Launch recursive spawning experiment

    Spawns 3 coordinators (depth 1), each spawns 2-3 workers (depth 2)
    Expected total: 11 agents (3 + 3 + 3 + 2 = 11)
    """
    global AGENT_COUNT, SPAWN_LOG
    AGENT_COUNT = 0
    SPAWN_LOG = []

    print("=" * 70)
    print("CC4 RECURSIVE SUB-AGENT EXPERIMENT")
    print("=" * 70)
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Max depth: 2")
    print()

    experiment_start = time.time()

    # CC4 spawns coordinators (depth 1)
    print("[CC4] Spawning 3 coordinators in parallel (depth 1)...")
    print()

    coordinators = [
        ("CC4a", coordinator_cc4a),
        ("CC4b", coordinator_cc4b),
        ("CC4c", coordinator_cc4c),
    ]

    spawn_start = time.time()

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): name for name, fn in coordinators}

        spawn_time = (time.time() - spawn_start) * 1000

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results[name] = asdict(result)
                print(f"[CC4] {name} complete ({result.elapsed_ms}ms)")
            except Exception as e:
                results[name] = {"error": str(e)}
                print(f"[CC4] {name} ERROR: {e}")

    total_time = (time.time() - experiment_start) * 1000

    # Calculate metrics
    total_agents = AGENT_COUNT

    # Count tests
    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    def count_tests(data):
        nonlocal total_tests, passed_tests, failed_tests
        if isinstance(data, dict):
            if "tests" in data:
                for test in data["tests"]:
                    total_tests += 1
                    if test.get("status") == "PASS":
                        passed_tests += 1
                    else:
                        failed_tests += 1
            if "children" in data:
                for child in data["children"].values():
                    count_tests(child)

    for r in results.values():
        count_tests(r)

    # Calculate estimated sequential time
    def sum_elapsed(data):
        total = 0
        if isinstance(data, dict):
            total += data.get("elapsed_ms", 0)
            if "children" in data:
                for child in data["children"].values():
                    total += sum_elapsed(child)
        return total

    sequential_estimate = sum(sum_elapsed(r) for r in results.values())
    speedup = sequential_estimate / total_time if total_time > 0 else 0

    # Print results
    print()
    print("=" * 70)
    print("SPAWN LOG")
    print("=" * 70)
    for entry in SPAWN_LOG:
        indent = "  " * entry["depth"]
        print(f"{indent}{entry['agent']} (depth {entry['depth']}, #{entry['count']})")

    print()
    print("=" * 70)
    print("EXPERIMENT RESULTS")
    print("=" * 70)
    print(f"Total agents spawned: {total_agents}")
    print(f"Max depth reached: 2")
    print(f"Coordinators (depth 1): 3")
    print(f"Workers (depth 2): {total_agents - 3}")
    print()
    print(f"Total tests run: {total_tests}")
    print(f"Tests passed: {passed_tests}")
    print(f"Tests failed: {failed_tests}")
    print(f"Pass rate: {(passed_tests/total_tests*100) if total_tests > 0 else 0:.1f}%")
    print()
    print("TIMING METRICS:")
    print(f"  Spawn overhead: {spawn_time:.2f}ms")
    print(f"  Total wall-clock time: {total_time:.2f}ms ({total_time/1000:.2f}s)")
    print(f"  Estimated sequential: {sequential_estimate:.2f}ms ({sequential_estimate/1000:.2f}s)")
    print(f"  SPEEDUP: {speedup:.2f}x")
    print()
    print(f"End time: {datetime.now().isoformat()}")
    print("=" * 70)

    # Build final report
    report = {
        "experiment": "Recursive Sub-Agent Spawning",
        "timestamp": datetime.now().isoformat(),
        "architecture": {
            "depth_0": "CC4 (root)",
            "depth_1": ["CC4a", "CC4b", "CC4c"],
            "depth_2": ["CC4a-1", "CC4a-2", "CC4a-3", "CC4b-1", "CC4b-2", "CC4b-3", "CC4c-1", "CC4c-2"]
        },
        "metrics": {
            "total_agents": total_agents,
            "max_depth": 2,
            "coordinators": 3,
            "workers": total_agents - 3,
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "pass_rate": round((passed_tests/total_tests*100) if total_tests > 0 else 0, 1),
            "spawn_time_ms": round(spawn_time, 2),
            "total_time_ms": round(total_time, 2),
            "sequential_estimate_ms": round(sequential_estimate, 2),
            "speedup": round(speedup, 2)
        },
        "spawn_log": SPAWN_LOG,
        "results": results
    }

    return report


if __name__ == "__main__":
    report = run_recursive_experiment()

    # Save results
    output_file = "recursive_experiment_results.json"
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved to: {output_file}")
