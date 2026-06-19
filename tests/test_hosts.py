from utils.hosts import (
	HOST_OVERRIDES_ENV,
	get_browser_host_resolver_args,
	get_host_resolver_rules_arg,
	parse_host_overrides,
)


def test_parse_single_entry():
	assert parse_host_overrides('47.246.23.200 anyrouter.top') == [('anyrouter.top', '47.246.23.200')]


def test_parse_handles_none_and_empty():
	assert parse_host_overrides(None) == []
	assert parse_host_overrides('') == []
	assert parse_host_overrides('   ') == []


def test_parse_multiple_via_newline_and_semicolon():
	raw = '47.246.23.200 anyrouter.top\n1.2.3.4 example.com ; 5.6.7.8 foo.test'
	assert parse_host_overrides(raw) == [
		('anyrouter.top', '47.246.23.200'),
		('example.com', '1.2.3.4'),
		('foo.test', '5.6.7.8'),
	]


def test_parse_skips_comments_and_malformed_lines():
	raw = '# comment line\n\n47.246.23.200 anyrouter.top\nonlyonefield\n'
	assert parse_host_overrides(raw) == [('anyrouter.top', '47.246.23.200')]


def test_parse_multiple_hostnames_per_ip():
	assert parse_host_overrides('1.2.3.4 a.test b.test') == [('a.test', '1.2.3.4'), ('b.test', '1.2.3.4')]


def test_resolver_rules_arg_when_set(monkeypatch):
	monkeypatch.setenv(HOST_OVERRIDES_ENV, '47.246.23.200 anyrouter.top')
	assert get_host_resolver_rules_arg() == '--host-resolver-rules=MAP anyrouter.top 47.246.23.200'
	assert get_browser_host_resolver_args() == ['--host-resolver-rules=MAP anyrouter.top 47.246.23.200']


def test_resolver_rules_arg_joins_multiple(monkeypatch):
	monkeypatch.setenv(HOST_OVERRIDES_ENV, '47.246.23.200 anyrouter.top; 1.2.3.4 example.com')
	assert get_host_resolver_rules_arg() == (
		'--host-resolver-rules=MAP anyrouter.top 47.246.23.200,MAP example.com 1.2.3.4'
	)


def test_resolver_rules_arg_when_unset(monkeypatch):
	monkeypatch.delenv(HOST_OVERRIDES_ENV, raising=False)
	assert get_host_resolver_rules_arg() is None
	assert get_browser_host_resolver_args() == []
