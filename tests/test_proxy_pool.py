import json
from datetime import datetime, timedelta, timezone

import utils.proxy_pool as proxy_pool
from utils.proxy_pool import is_pool_fresh, normalize_proxy, parse_proxy_source, proxy_pool_candidates


def test_normalize_proxy_accepts_only_public_ipv4_http_endpoints():
	assert normalize_proxy('120.232.115.170:17981') == 'http://120.232.115.170:17981'
	assert normalize_proxy('https://8.8.8.8:443') == 'https://8.8.8.8:443'
	assert normalize_proxy('127.0.0.1:8080') is None
	assert normalize_proxy('socks5://120.232.115.170:17981') is None
	assert normalize_proxy('proxy.example:8080') is None


def test_parse_proxy_source_deduplicates_and_filters_lines():
	content = '\n'.join(
		[
			'120.232.115.170:17981',
			'http://120.232.115.170:17981',
			'127.0.0.1:8080',
			'not-a-proxy',
		]
	)

	assert parse_proxy_source(content) == ['http://120.232.115.170:17981']


def test_proxy_pool_candidates_require_fresh_expiration(tmp_path):
	now = datetime.now(timezone.utc)
	pool_path = tmp_path / 'proxy_pool.json'
	pool_path.write_text(
		json.dumps(
			{
				'expires_at': (now + timedelta(hours=1)).isoformat(),
				'proxies': ['http://120.232.115.170:17981'],
			}
		),
		encoding='utf-8',
	)

	pool = json.loads(pool_path.read_text(encoding='utf-8'))
	assert is_pool_fresh(pool, now=now)
	assert proxy_pool_candidates(pool_path) == ['http://120.232.115.170:17981']

	pool['expires_at'] = (now - timedelta(seconds=1)).isoformat()
	pool_path.write_text(json.dumps(pool), encoding='utf-8')
	assert not is_pool_fresh(pool, now=now)
	assert proxy_pool_candidates(pool_path) == []


def test_refresh_keeps_existing_pool_when_a_source_cannot_be_compared(monkeypatch, tmp_path):
	now = datetime.now(timezone.utc)
	pool_path = tmp_path / 'proxy_pool.json'
	existing = {
		'expires_at': (now + timedelta(hours=1)).isoformat(),
		'proxies': ['http://120.232.115.170:17981'],
		'source_revisions': {'source-a': 'old-a', 'source-b': 'old-b'},
	}
	pool_path.write_text(json.dumps(existing), encoding='utf-8')

	def fake_fetch(url, **kwargs):
		if url == 'source-b':
			raise OSError('offline')
		return ['http://120.232.115.170:17981'], {'sha256': 'new-a'}

	monkeypatch.setattr(proxy_pool, 'fetch_proxy_source', fake_fetch)

	changed, pool = proxy_pool.refresh_proxy_pool(
		pool_path,
		source_urls=('source-a', 'source-b'),
	)

	assert changed is False
	assert pool == existing
	assert json.loads(pool_path.read_text(encoding='utf-8')) == existing


def test_probe_accepts_json_response_with_non_auth_status(monkeypatch):
	class FakeResponse:
		status_code = 200
		headers = {'content-type': 'application/json'}

		@staticmethod
		def json():
			return {'success': False}

	class FakeClient:
		def __init__(self, **kwargs):
			pass

		def __enter__(self):
			return self

		def __exit__(self, *args):
			return False

		def get(self, *args, **kwargs):
			return FakeResponse()

	monkeypatch.setattr(proxy_pool.httpx, 'Client', FakeClient)
	assert proxy_pool.probe_proxy('http://8.8.8.8:80') is True
