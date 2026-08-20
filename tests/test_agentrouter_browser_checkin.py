import pytest

import checkin
from utils.config import AccountConfig, AppConfig, ProviderConfig


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


@pytest.mark.asyncio
async def test_browser_auto_check_in_keeps_browser_waf_cookie(monkeypatch):
	class FakeContext:
		def __init__(self):
			self.added_cookies = []

		async def add_cookies(self, cookies):
			self.added_cookies.extend(cookies)

	class FakePage:
		def __init__(self):
			self.context = FakeContext()
			self.goto_calls = []
			self.evaluate_calls = []

		async def goto(self, url, **kwargs):
			self.goto_calls.append((url, kwargs))

		async def evaluate(self, script, arguments):
			self.evaluate_calls.append((script, arguments))
			return {
				'status': 200,
				'contentType': 'application/json; charset=utf-8',
				'text': '{"success":true,"data":{"quota":500000,"used_quota":0}}',
			}

	class FakeBrowser:
		def __init__(self):
			self.page = FakePage()
			self.closed = False

		async def new_page(self):
			return self.page

		async def close(self):
			self.closed = True

	browser = FakeBrowser()
	launch_kwargs = {}

	async def fake_launch_async(**kwargs):
		launch_kwargs.update(kwargs)
		return browser

	async def async_noop(*args, **kwargs):
		return None

	monkeypatch.setattr(checkin, 'launch_async', fake_launch_async)
	monkeypatch.setattr(checkin, 'prepare_browser_page', async_noop)
	monkeypatch.setattr(checkin, 'wait_for_waf_ready', async_noop)
	monkeypatch.setattr(checkin.asyncio, 'sleep', async_noop)
	monkeypatch.setattr(checkin, 'get_playwright_proxy', lambda **kwargs: None)

	provider = ProviderConfig(
		name='agentrouter',
		domain='https://ps.air-outer.com',
		sign_in_path=None,
		bypass_method='waf_cookies',
		waf_cookie_names=['acw_tc'],
	)
	account = AccountConfig(
		cookies={'session': 'session-value'},
		api_user='434852',
		provider='agentrouter',
	)

	result = await checkin.run_browser_auto_check_in(
		{'session': 'session-value', 'acw_tc': 'browser-cookie-from-another-context'},
		account,
		'Account 2',
		provider,
	)

	assert result[0] is True
	assert launch_kwargs == {'headless': True}
	assert browser.closed is True
	assert browser.page.context.added_cookies == [
		{'name': 'session', 'value': 'session-value', 'url': 'https://ps.air-outer.com'}
	]
	assert len(browser.page.evaluate_calls) == 2
	assert browser.page.evaluate_calls[0][1]['apiUser'] == '434852'


@pytest.mark.asyncio
async def test_check_in_account_routes_waf_auto_provider_to_browser(monkeypatch):
	provider = ProviderConfig(
		name='agentrouter',
		domain='https://ps.air-outer.com',
		sign_in_path=None,
		bypass_method='waf_cookies',
		waf_cookie_names=['acw_tc'],
	)
	account = AccountConfig(
		cookies={'session': 'session-value'},
		api_user='434852',
		provider='agentrouter',
	)
	captured = {}

	async def fake_browser_check_in(all_cookies, passed_account, account_name, passed_provider, **kwargs):
		captured['cookies'] = all_cookies
		captured['account'] = passed_account
		captured['account_name'] = account_name
		captured['provider'] = passed_provider
		return True, {'success': True}, {'success': True}

	async def unexpected_prepare_cookies(*args, **kwargs):
		raise AssertionError('HTTP WAF cookie preparation should be skipped')

	monkeypatch.setattr(checkin, 'run_browser_auto_check_in', fake_browser_check_in)
	monkeypatch.setattr(checkin, 'prepare_cookies', unexpected_prepare_cookies)

	result = await checkin.check_in_account(account, 1, AppConfig(providers={'agentrouter': provider}))

	assert result[0] is True
	assert captured['cookies'] == {'session': 'session-value'}
	assert captured['account'] is account
	assert captured['account_name'] == 'Account 2'
	assert captured['provider'] is provider
