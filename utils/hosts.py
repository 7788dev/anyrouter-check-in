"""自定义 host 解析。

用于域名过期 / DNS 失效等场景：把域名固定解析到指定 IP，等价于在
系统 hosts 文件中写入一条记录。

读取环境变量 ``CHECKIN_HOST_OVERRIDES``，格式与 /etc/hosts 一致：

    47.246.23.200 anyrouter.top

多条记录可用换行或英文分号分隔：

    47.246.23.200 anyrouter.top; 1.2.3.4 example.com

httpx（标准 socket 解析）在 CI/本地都会读取系统 hosts 文件，因此只要
GitHub Actions 步骤写入 /etc/hosts 即可生效；本模块额外把同样的映射转换为
Chromium 的 ``--host-resolver-rules`` 参数，保证 CloakBrowser 内核也走相同解析，
做到浏览器与 HTTP 客户端双重兜底。
"""

from __future__ import annotations

import os

HOST_OVERRIDES_ENV = 'CHECKIN_HOST_OVERRIDES'


def parse_host_overrides(raw: str | None) -> list[tuple[str, str]]:
	"""解析 hosts 格式文本，返回 ``(hostname, ip)`` 列表。

	支持换行或英文分号分隔多条记录；以 ``#`` 开头的行视为注释。
	"""
	if not raw:
		return []

	overrides: list[tuple[str, str]] = []
	for entry in raw.replace(';', '\n').splitlines():
		line = entry.strip()
		if not line or line.startswith('#'):
			continue
		parts = line.split()
		if len(parts) < 2:
			continue
		ip = parts[0]
		for hostname in parts[1:]:
			overrides.append((hostname, ip))
	return overrides


def get_host_overrides() -> list[tuple[str, str]]:
	"""从环境变量读取自定义 host 映射。"""
	return parse_host_overrides(os.getenv(HOST_OVERRIDES_ENV))


def get_host_resolver_rules_arg() -> str | None:
	"""构造 Chromium ``--host-resolver-rules`` 启动参数。

	返回形如 ``--host-resolver-rules=MAP anyrouter.top 47.246.23.200`` 的字符串；
	未配置任何映射时返回 ``None``。
	"""
	overrides = get_host_overrides()
	if not overrides:
		return None
	rules = ','.join(f'MAP {hostname} {ip}' for hostname, ip in overrides)
	return f'--host-resolver-rules={rules}'


def get_browser_host_resolver_args() -> list[str]:
	"""返回浏览器启动需要追加的 host 解析参数列表（无配置时为空列表）。"""
	arg = get_host_resolver_rules_arg()
	return [arg] if arg else []
