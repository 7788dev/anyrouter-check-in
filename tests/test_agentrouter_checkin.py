from types import SimpleNamespace

import checkin


def test_parse_user_info_response_reports_waf_html():
	result = checkin.parse_user_info_response(
		200,
		'<!doctype html><meta name="aliyun_waf_aa">',
		'text/html; charset=utf-8',
		16000,
	)

	assert result['success'] is False
	assert 'HTTP 200 returned non-JSON response' in result['error']
	assert 'content-type=text/html' in result['error']
	assert 'body=16000 bytes' in result['error']


def test_parse_user_info_response_extracts_balances():
	result = checkin.parse_user_info_response(
		200,
		'{"success":true,"data":{"quota":12500000,"used_quota":2500000}}',
		'application/json',
	)

	assert result == {
		'success': True,
		'quota': 25.0,
		'used_quota': 5.0,
		'display': ':money: Current balance: $25.0, Used: $5.0',
	}


def test_http_warmup_uses_same_client_and_browser_headers():
	class FakeClient:
		def __init__(self):
			self.calls = []
			self.cookies = SimpleNamespace(jar=[])

		def get(self, url, **kwargs):
			self.calls.append((url, kwargs))
			self.cookies.jar.append(SimpleNamespace(name='acw_tc'))
			return SimpleNamespace(
				status_code=200,
				headers={'content-type': 'text/html; charset=utf-8'},
				content=b'<html></html>',
			)

	client = FakeClient()
	provider = SimpleNamespace(
		http_warmup=True,
		domain='https://ps.air-outer.com',
		login_path='/login',
		waf_cookie_names=['acw_tc'],
	)
	headers = {
		'User-Agent': 'test-user-agent',
		'Accept-Language': 'zh-CN',
		'Accept-Encoding': 'gzip, deflate, br, zstd',
	}

	checkin.warm_up_http_session(client, 'Account 2', provider, headers)

	assert client.calls == [
		(
			'https://ps.air-outer.com/login',
			{
				'headers': {
					'User-Agent': 'test-user-agent',
					'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
					'Accept-Language': 'zh-CN',
					'Accept-Encoding': 'gzip, deflate, br, zstd',
					'Connection': 'keep-alive',
					'Sec-Fetch-Dest': 'document',
					'Sec-Fetch-Mode': 'navigate',
					'Sec-Fetch-Site': 'none',
					'Sec-Fetch-User': '?1',
					'Upgrade-Insecure-Requests': '1',
				},
				'timeout': 30,
			},
		)
	]


def test_http_warmup_warns_when_expected_cookie_is_missing(capsys):
	class FakeClient:
		cookies = SimpleNamespace(jar=[])

		def get(self, *args, **kwargs):
			return SimpleNamespace(status_code=200, headers={}, content=b'challenge')

	provider = SimpleNamespace(
		http_warmup=True,
		domain='https://ps.air-outer.com',
		login_path='/login',
		waf_cookie_names=['acw_tc'],
	)
	headers = {
		'User-Agent': 'test-user-agent',
		'Accept-Language': 'zh-CN',
		'Accept-Encoding': 'gzip',
	}

	checkin.warm_up_http_session(FakeClient(), 'Account 2', provider, headers)

	output = capsys.readouterr().out
	assert 'waf-cookies=none' in output
	assert 'did not receive an expected WAF cookie' in output


def test_http_warmup_can_be_disabled():
	class UnexpectedClient:
		def get(self, *args, **kwargs):
			raise AssertionError('warm-up request should be skipped')

	provider = SimpleNamespace(http_warmup=False)
	checkin.warm_up_http_session(UnexpectedClient(), 'Account 1', provider, {})
