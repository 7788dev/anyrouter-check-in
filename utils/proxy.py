"""代理配置：读取环境变量并供浏览器 / HTTP 客户端使用。"""

from __future__ import annotations

import os
import random

from utils.proxy_pool import proxy_pool_candidates


def get_proxy_candidates(*, use_proxy: bool = True, provider_name: str | None = None) -> list[str | None]:
	"""Return explicit or pool-backed proxy candidates in randomized order."""
	if not use_proxy:
		return [None]
	server = os.getenv('CHECKIN_PROXY_URL', '').strip()
	if server:
		return [server]
	if provider_name != 'agentrouter':
		return [None]
	candidates = proxy_pool_candidates()
	random.SystemRandom().shuffle(candidates)
	return candidates


def get_proxy_server(*, use_proxy: bool = True, provider_name: str | None = None) -> str | None:
	"""Return the first configured proxy; use_proxy=False disables proxying."""
	return get_proxy_candidates(use_proxy=use_proxy, provider_name=provider_name)[0]


def get_playwright_proxy(*, use_proxy: bool = True, provider_name: str | None = None) -> dict[str, str] | None:
	server = get_proxy_server(use_proxy=use_proxy, provider_name=provider_name)
	if not server:
		return None
	return {'server': server}
