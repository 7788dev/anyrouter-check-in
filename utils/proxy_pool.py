"""Public HTTP proxy pool discovery and validation for AgentRouter."""

from __future__ import annotations

import hashlib
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, ip_address
from pathlib import Path

import httpx

DEFAULT_POOL_PATH = Path('proxy_pool.json')
DEFAULT_TARGET_URL = 'https://ps.air-outer.com/api/user/self'
DEFAULT_SOURCE_URLS = (
	'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
	'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
	'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt',
)
DEFAULT_POOL_TTL_HOURS = 36
DEFAULT_SOURCE_TIMEOUT = 20.0
DEFAULT_PROBE_TIMEOUT = 7.0
DEFAULT_MAX_CANDIDATES = 600
DEFAULT_WORKERS = 48
_PROXY_LINE_RE = re.compile(r'^(?:(?P<scheme>https?)://)?(?P<host>[^:/\s]+):(?P<port>\d{1,5})$')


def utc_now() -> datetime:
	return datetime.now(timezone.utc)


def _parse_timestamp(value: object) -> datetime | None:
	if not isinstance(value, str) or not value.strip():
		return None
	try:
		parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
	except ValueError:
		return None
	if parsed.tzinfo is None:
		return parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def normalize_proxy(value: str) -> str | None:
	"""Return a safe public HTTP proxy URL, or None for unsupported input."""
	if not isinstance(value, str):
		return None
	match = _PROXY_LINE_RE.fullmatch(value.strip())
	if not match:
		return None

	host = match.group('host')
	try:
		address = ip_address(host)
		port = int(match.group('port'))
	except ValueError:
		return None
	if not isinstance(address, IPv4Address) or not address.is_global or not 1 <= port <= 65535:
		return None

	scheme = match.group('scheme') or 'http'
	return f'{scheme}://{address}:{port}'


def parse_proxy_source(content: str) -> list[str]:
	proxies: list[str] = []
	seen: set[str] = set()
	for line in content.splitlines():
		proxy = normalize_proxy(line)
		if proxy and proxy not in seen:
			seen.add(proxy)
			proxies.append(proxy)
	return proxies


def _source_headers(response: httpx.Response) -> dict[str, str]:
	return {
		'etag': response.headers.get('etag', ''),
		'last_modified': response.headers.get('last-modified', ''),
	}


def fetch_proxy_source(url: str, *, timeout: float = DEFAULT_SOURCE_TIMEOUT) -> tuple[list[str], dict[str, str]]:
	with httpx.Client(
		timeout=timeout,
		follow_redirects=True,
		trust_env=False,
		headers={'User-Agent': 'anyrouter-check-in/proxy-pool'},
	) as client:
		response = client.get(url)
		response.raise_for_status()
	content = response.text
	metadata = _source_headers(response)
	metadata['sha256'] = hashlib.sha256(content.encode('utf-8')).hexdigest()
	return parse_proxy_source(content), metadata


def probe_proxy(
	proxy_url: str,
	*,
	target_url: str = DEFAULT_TARGET_URL,
	timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> bool:
	"""Validate a proxy without sending account cookies."""
	try:
		with httpx.Client(
			proxy=proxy_url,
			http2=True,
			follow_redirects=True,
			trust_env=False,
			timeout=timeout,
			headers={
				'Accept': 'application/json, text/plain, */*',
				'User-Agent': 'anyrouter-check-in/proxy-probe',
			},
		) as client:
			response = client.get(target_url)
			content_type = response.headers.get('content-type', '').lower()
			if response.status_code >= 500 or 'json' not in content_type:
				return False
			payload = response.json()
			return isinstance(payload, dict)
	except (httpx.HTTPError, ValueError, TypeError):
		return False


def _probe_all(
	proxies: list[str],
	*,
	target_url: str,
	workers: int,
	probe_timeout: float,
) -> list[str]:
	valid: list[str] = []
	with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
		futures = {
			executor.submit(probe_proxy, proxy, target_url=target_url, timeout=probe_timeout): proxy
			for proxy in proxies
		}
		for future in as_completed(futures):
			proxy = futures[future]
			try:
				if future.result():
					valid.append(proxy)
			except Exception:  # nosec B112 - one bad public proxy must not abort the pool
				continue
	return sorted(valid)


def load_proxy_pool(path: Path = DEFAULT_POOL_PATH) -> dict | None:
	try:
		with path.open('r', encoding='utf-8') as handle:
			pool = json.load(handle)
	except (OSError, json.JSONDecodeError):
		return None
	if not isinstance(pool, dict) or not isinstance(pool.get('proxies'), list):
		return None
	return pool


def is_pool_fresh(pool: dict | None, *, now: datetime | None = None) -> bool:
	if not pool or not pool.get('proxies'):
		return False
	expires_at = _parse_timestamp(pool.get('expires_at'))
	return expires_at is not None and expires_at > (now or utc_now())


def _pool_source_revisions(pool: dict | None) -> dict[str, str]:
	if not pool or not isinstance(pool.get('source_revisions'), dict):
		return {}
	return {
		str(url): str(revision)
		for url, revision in pool['source_revisions'].items()
		if isinstance(url, str) and isinstance(revision, str)
	}


def _write_pool(path: Path, pool: dict) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary_path = path.with_name(f'{path.name}.tmp')
	with temporary_path.open('w', encoding='utf-8', newline='\n') as handle:
		json.dump(pool, handle, ensure_ascii=True, indent=2, sort_keys=True)
		handle.write('\n')
	temporary_path.replace(path)


def refresh_proxy_pool(
	path: Path = DEFAULT_POOL_PATH,
	*,
	source_urls: tuple[str, ...] = DEFAULT_SOURCE_URLS,
	target_url: str = DEFAULT_TARGET_URL,
	ttl_hours: int = DEFAULT_POOL_TTL_HOURS,
	max_candidates: int = DEFAULT_MAX_CANDIDATES,
	workers: int = DEFAULT_WORKERS,
	probe_timeout: float = DEFAULT_PROBE_TIMEOUT,
	force: bool = False,
) -> tuple[bool, dict | None]:
	"""Fetch sources and update the pool only when a source or its TTL changed."""
	existing = load_proxy_pool(path)
	sources: dict[str, dict[str, str]] = {}
	candidates: set[str] = set()
	priority_candidates: list[str] = []
	failed_sources: list[str] = []
	for source_url in source_urls:
		try:
			proxies, metadata = fetch_proxy_source(source_url)
		except (httpx.HTTPError, OSError) as exc:
			failed_sources.append(f'{source_url}: {type(exc).__name__}')
			continue
		sources[source_url] = metadata
		candidates.update(proxies)
		for proxy in proxies[:80]:
			if proxy not in priority_candidates:
				priority_candidates.append(proxy)

	if not sources:
		print('[WARN] No proxy source could be fetched')
		return False, existing

	existing_revisions = _pool_source_revisions(existing)
	source_revisions = {url: metadata['sha256'] for url, metadata in sources.items()}
	if failed_sources:
		print(f'[WARN] Failed proxy sources: {len(failed_sources)}')
		if not force and existing_revisions:
			print('[INFO] Keeping the existing pool until every configured source can be compared')
			return False, existing
	if not force and is_pool_fresh(existing) and existing_revisions == source_revisions:
		print('[INFO] Proxy sources unchanged and existing pool is fresh; no update needed')
		return False, existing

	candidate_limit = max(1, max_candidates)
	selected_candidates: list[str] = []
	existing_proxies = existing.get('proxies', []) if isinstance(existing, dict) else []
	for proxy in [*existing_proxies, *priority_candidates]:
		if proxy in candidates and proxy not in selected_candidates:
			selected_candidates.append(proxy)
		if len(selected_candidates) >= candidate_limit:
			break
	remaining_candidates = sorted(candidates - set(selected_candidates))
	remaining_slots = candidate_limit - len(selected_candidates)
	if remaining_slots > 0:
		if len(remaining_candidates) > remaining_slots:
			remaining_candidates = random.SystemRandom().sample(remaining_candidates, remaining_slots)
		selected_candidates.extend(remaining_candidates)
	print(f'[INFO] Validating {len(selected_candidates)} public proxy candidate(s)')
	valid_proxies = _probe_all(
		selected_candidates,
		target_url=target_url,
		workers=workers,
		probe_timeout=probe_timeout,
	)
	if not valid_proxies:
		print('[WARN] No usable proxy found; keeping the previous pool')
		return False, existing

	now = utc_now()
	pool = {
		'schema_version': 1,
		'generated_at': now.isoformat().replace('+00:00', 'Z'),
		'expires_at': (now + timedelta(hours=max(1, ttl_hours))).isoformat().replace('+00:00', 'Z'),
		'target_url': target_url,
		'source_revisions': source_revisions,
		'source_metadata': sources,
		'proxies': valid_proxies,
	}
	_write_pool(path, pool)
	print(f'[SUCCESS] Wrote {len(valid_proxies)} usable proxy(s) to {path}')
	return True, pool


def proxy_pool_candidates(path: Path = DEFAULT_POOL_PATH) -> list[str]:
	pool = load_proxy_pool(path)
	if not is_pool_fresh(pool):
		return []
	return [proxy for proxy in pool.get('proxies', []) if normalize_proxy(proxy)]
