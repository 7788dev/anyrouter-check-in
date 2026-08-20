import json

from utils.config import AppConfig, ProviderConfig


def test_builtin_provider_profile_persistence_defaults(monkeypatch):
	monkeypatch.delenv('PROVIDERS', raising=False)

	config = AppConfig.load_from_env()

	assert config.providers['anyrouter'].persist_profile is True
	assert config.providers['agentrouter'].persist_profile is False


def test_builtin_agentrouter_uses_proxy_pool_for_air_outer_endpoint(monkeypatch):
	monkeypatch.delenv('PROVIDERS', raising=False)

	config = AppConfig.load_from_env()
	provider = config.providers['agentrouter']

	assert provider.domain == 'https://ps.air-outer.com'
	assert provider.use_proxy is True
	assert provider.waf_cookie_names == ['acw_tc']
	assert provider.needs_waf_cookies() is False
	assert provider.http_warmup is True


def test_provider_profile_persistence_can_override_builtin(monkeypatch):
	monkeypatch.setenv(
		'PROVIDERS',
		json.dumps(
			{
				'anyrouter': {'domain': 'https://anyrouter.top', 'persist_profile': False},
				'agentrouter': {'domain': 'https://ps.air-outer.com', 'persist_profile': True},
			}
		),
	)

	config = AppConfig.load_from_env()

	assert config.providers['anyrouter'].persist_profile is False
	assert config.providers['agentrouter'].persist_profile is True


def test_custom_provider_profile_persistence_defaults_to_false(monkeypatch):
	monkeypatch.setenv('PROVIDERS', json.dumps({'custom': {'domain': 'https://custom.example.com'}}))

	config = AppConfig.load_from_env()

	assert config.providers['custom'].persist_profile is False


def test_provider_from_dict_inherits_profile_persistence_from_defaults():
	defaults = ProviderConfig(name='custom', domain='https://old.example.com', persist_profile=True)

	provider = ProviderConfig.from_dict(
		'custom',
		{'domain': 'https://new.example.com'},
		defaults=defaults,
	)

	assert provider.persist_profile is True


def test_agentrouter_account_override_replaces_existing_agentrouter_account(monkeypatch):
	monkeypatch.setenv(
		'ANYROUTER_ACCOUNTS',
		json.dumps(
			[
				{'provider': 'anyrouter', 'cookies': {'session': 'any'}, 'api_user': '1'},
				{'provider': 'agentrouter', 'cookies': {'session': 'old'}, 'api_user': '2'},
			]
		),
	)
	monkeypatch.setenv(
		'AGENTROUTER_ACCOUNT',
		json.dumps({'cookies': {'session': 'new'}, 'api_user': '3'}),
	)

	from utils.config import load_accounts_config

	accounts = load_accounts_config()

	assert accounts is not None
	assert [(account.provider, account.api_user) for account in accounts] == [('anyrouter', '1'), ('agentrouter', '3')]
