#!/usr/bin/env python3
"""Refresh the checked public proxy pool used by AgentRouter."""

from __future__ import annotations

import argparse
from pathlib import Path

from utils.proxy_pool import (
	DEFAULT_MAX_CANDIDATES,
	DEFAULT_POOL_PATH,
	DEFAULT_POOL_TTL_HOURS,
	DEFAULT_SOURCE_URLS,
	DEFAULT_WORKERS,
	refresh_proxy_pool,
)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--path', type=Path, default=DEFAULT_POOL_PATH)
	parser.add_argument('--ttl-hours', type=int, default=DEFAULT_POOL_TTL_HOURS)
	parser.add_argument('--max-candidates', type=int, default=DEFAULT_MAX_CANDIDATES)
	parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS)
	parser.add_argument('--force', action='store_true')
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	refresh_proxy_pool(
		args.path,
		source_urls=DEFAULT_SOURCE_URLS,
		ttl_hours=args.ttl_hours,
		max_candidates=args.max_candidates,
		workers=args.workers,
		force=args.force,
	)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
