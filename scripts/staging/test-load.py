#!/usr/bin/env python3
"""Bounded HTTP load smoke test for a staging URL (never calls an AI provider itself).

Use a seeded non-admin staging tester token and target /api/chats. This records status and latency only;
it does not print response bodies, authorization headers, or token values.
"""
import argparse
import concurrent.futures
import os
import statistics
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True, help='for example https://staging.example.com/api/chats')
    parser.add_argument('--token-env', default='STAGING_TEST_TOKEN', help='environment variable holding a short-lived token')
    parser.add_argument('--requests', type=int, default=100)
    parser.add_argument('--concurrency', type=int, default=10)
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not args.url.startswith('https://') or not 1 <= args.requests <= 1000 or not 1 <= args.concurrency <= 25:
        parser.error('require HTTPS, requests 1..1000, and concurrency 1..25')
    if not token:
        parser.error(f'set {args.token_env} in the environment; tokens must not be passed on the command line')

    def request(_):
        req = urllib.request.Request(args.url, headers={'Authorization': f'Bearer {token}'})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                response.read(4096)
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.read(4096)
        except Exception as exc:
            return type(exc).__name__, time.perf_counter() - start
        return str(status), time.perf_counter() - start

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(request, range(args.requests)))
    elapsed = time.perf_counter() - start
    latencies = sorted(t for _, t in results)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * .95))]
    statuses = {}
    for status, _ in results:
        statuses[status] = statuses.get(status, 0) + 1
    print(f"requests={len(results)} concurrency={args.concurrency} seconds={elapsed:.2f} rps={len(results)/elapsed:.2f}")
    print(f"status_counts={statuses} p50_ms={statistics.median(latencies)*1000:.1f} p95_ms={p95*1000:.1f}")
    return 0 if all(status == '200' for status, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
