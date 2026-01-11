"""
Load test comparing blocking vs async endpoints.

Usage:
    uv run python load_test.py sample.pdf [num_requests]
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx
import matplotlib.pyplot as plt

BASE_URL = "http://127.0.0.1:8000"


async def check_server(client: httpx.AsyncClient) -> bool:
    try:
        response = await client.get("/health", timeout=5.0)
        return response.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def upload_pdf(
    client: httpx.AsyncClient,
    endpoint: str,
    pdf_path: Path,
    request_id: int,
) -> float | None:
    start = time.perf_counter()
    try:
        with open(pdf_path, "rb") as f:
            response = await client.post(
                endpoint,
                files={"file": (pdf_path.name, f, "application/pdf")},
            )
        elapsed = time.perf_counter() - start
        if response.status_code != 200:
            print(f"  Request {request_id}: FAILED {response.status_code}")
            return None
        return elapsed
    except httpx.ReadError:
        print(f"  Request {request_id}: Server closed connection")
        return None
    except Exception as e:
        print(f"  Request {request_id}: {e}")
        return None


async def run_test(
    client: httpx.AsyncClient,
    endpoint: str,
    pdf_path: Path,
    num_requests: int,
) -> list[float]:
    tasks = [upload_pdf(client, endpoint, pdf_path, i + 1) for i in range(num_requests)]
    results = await asyncio.gather(*tasks)
    return [t for t in results if t is not None]


def percentile(data: list[float], p: float) -> float:
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


def plot_results(
    blocking_times: list[float],
    async_times: list[float],
    blocking_total: float,
    async_total: float,
    output_path: str = "results.png",
):
    num_requests = len(blocking_times)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Left plot: Latency percentiles (p95, p99 show the improvement)
    percentiles = ["p95", "p99"]
    blocking_pcts = [percentile(blocking_times, 95), percentile(blocking_times, 99)]
    async_pcts = [percentile(async_times, 95), percentile(async_times, 99)]

    p95_improvement = ((blocking_pcts[0] - async_pcts[0]) / blocking_pcts[0]) * 100
    p99_improvement = ((blocking_pcts[1] - async_pcts[1]) / blocking_pcts[1]) * 100

    x = range(len(percentiles))
    width = 0.35
    bars1 = ax1.bar([i - width/2 for i in x], blocking_pcts, width, label="Blocking", color="#e74c3c")
    bars2 = ax1.bar([i + width/2 for i in x], async_pcts, width, label="Async", color="#27ae60")
    ax1.set_xticks(x)
    ax1.set_xticklabels(percentiles)
    ax1.set_ylabel("Latency (seconds)")
    ax1.set_title(f"Latency (-{p95_improvement:.0f}% p95, -{p99_improvement:.0f}% p99)")
    ax1.legend()
    ax1.bar_label(bars1, fmt="%.2f")
    ax1.bar_label(bars2, fmt="%.2f")
    ax1.grid(True, alpha=0.3, axis="y")

    # Right plot: Throughput (RPS)
    blocking_rps = num_requests / blocking_total
    async_rps = num_requests / async_total
    rps_improvement = ((async_rps - blocking_rps) / blocking_rps) * 100

    bars = ax2.bar(["Blocking", "Async"], [blocking_rps, async_rps], color=["#e74c3c", "#27ae60"])
    ax2.set_ylabel("Requests Per Second")
    ax2.set_title(f"Throughput (+{rps_improvement:.0f}% improvement)")
    ax2.bar_label(bars, fmt="%.1f")
    ax2.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"\nGraph saved to {output_path}")


def print_stats(name: str, times: list[float], total_time: float):
    if not times:
        print(f"\n{name}: All requests failed")
        return

    rps = len(times) / total_time

    print(f"\n{name}:")
    print(f"  p50: {percentile(times, 50):.2f}s | p95: {percentile(times, 95):.2f}s | p99: {percentile(times, 99):.2f}s")
    print(f"  Throughput: {rps:.1f} RPS")


async def main(pdf_path: Path, num_requests: int):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        print(f"Checking server at {BASE_URL}...")
        if not await check_server(client):
            print("\nServer not responding. Start it with:")
            print("  uvicorn pdf_ingest:app --reload")
            sys.exit(1)

        print(f"Running {num_requests} concurrent requests per endpoint...\n")

        print("Testing /ingest/blocking...")
        start = time.perf_counter()
        blocking_times = await run_test(
            client,
            "/ingest/blocking",
            pdf_path,
            num_requests,
        )
        blocking_total = time.perf_counter() - start
        print(f"  Completed in {blocking_total:.2f}s")

        print("\nTesting /ingest/async...")
        start = time.perf_counter()
        async_times = await run_test(client, "/ingest/async", pdf_path, num_requests)
        async_total = time.perf_counter() - start
        print(f"  Completed in {async_total:.2f}s")

    print("\n" + "=" * 50)
    print_stats("Blocking", blocking_times, blocking_total)
    print_stats("Async", async_times, async_total)

    # Show improvement
    blocking_rps = num_requests / blocking_total
    async_rps = num_requests / async_total
    rps_improvement = ((async_rps - blocking_rps) / blocking_rps) * 100

    p99_blocking = percentile(blocking_times, 99)
    p99_async = percentile(async_times, 99)
    p99_improvement = ((p99_blocking - p99_async) / p99_blocking) * 100

    print(f"\nImprovement: +{rps_improvement:.0f}% throughput, -{p99_improvement:.0f}% p99 latency")
    print("=" * 50)

    if blocking_times and async_times:
        script_dir = Path(__file__).parent
        output_path = script_dir / f"results_{num_requests}.png"
        plot_results(blocking_times, async_times, blocking_total, async_total, str(output_path))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_test.py <pdf_path> [num_requests]")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found")
        sys.exit(1)

    num_requests = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    asyncio.run(main(pdf_path, num_requests))
