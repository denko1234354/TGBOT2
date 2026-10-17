"""Настройка и проверка прокси для обхода блокировки Telegram API."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass

import aiohttp
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"
DEFAULT_TIMEOUT = 15.0


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    url: str | None
    check_on_start: bool
    check_url: str
    timeout: float


def load_proxy_config() -> ProxyConfig:
    raw = os.getenv("PROXY", "").strip()
    check_raw = os.getenv("PROXY_CHECK", "true").strip().lower()
    check_on_start = check_raw in ("1", "true", "yes", "on")
    check_url = os.getenv("PROXY_CHECK_URL", TELEGRAM_API_URL).strip() or TELEGRAM_API_URL

    try:
        timeout = float(os.getenv("PROXY_TIMEOUT", str(DEFAULT_TIMEOUT)))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    if not raw:
        return ProxyConfig(url=None, check_on_start=False, check_url=check_url, timeout=timeout)

    return ProxyConfig(url=raw, check_on_start=check_on_start, check_url=check_url, timeout=timeout)


def mask_proxy_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url

    scheme, rest = url.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://***@{host}"


def is_socks_proxy(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith(("socks4://", "socks5://", "socks://"))


def create_aiohttp_session(timeout: float) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))


async def check_proxy(
    proxy_url: str,
    check_url: str = TELEGRAM_API_URL,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[bool, str]:
    """Проверяет, доступен ли Telegram API через прокси."""
    try:
        if is_socks_proxy(proxy_url):
            try:
                from aiohttp_socks import ProxyConnector
            except ImportError:
                return False, "Для SOCKS-прокси установите: pip install aiohttp-socks"

            connector = ProxyConnector.from_url(proxy_url)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as session:
                async with session.get(check_url) as response:
                    if response.status < 500:
                        return True, f"SOCKS-прокси работает (HTTP {response.status})"
                    return False, f"Прокси ответил с ошибкой HTTP {response.status}"

        async with create_aiohttp_session(timeout) as session:
            async with session.get(check_url, proxy=proxy_url) as response:
                if response.status < 500:
                    return True, f"HTTP-прокси работает (HTTP {response.status})"
                return False, f"Прокси ответил с ошибкой HTTP {response.status}"

    except asyncio.TimeoutError:
        return False, f"Таймаут ({timeout}с) — прокси не отвечает"
    except aiohttp.ClientProxyConnectionError as exc:
        return False, f"Не удалось подключиться к прокси: {exc}"
    except OSError as exc:
        return False, f"Сетевая ошибка: {exc}"
    except Exception as exc:
        return False, f"Ошибка: {type(exc).__name__}: {exc}"


def create_bot_session(proxy_url: str | None):
    if not proxy_url:
        return None

    from aiogram.client.session.aiohttp import AiohttpSession

    try:
        return AiohttpSession(proxy=proxy_url)
    except ImportError:
        logger.error(
            "Для работы через прокси установите: pip install aiohttp-socks",
        )
        raise SystemExit(1) from None


async def resolve_bot_session() -> tuple[object | None, str]:
    """Возвращает (session, mode). session=None — прямое подключение."""
    config = load_proxy_config()

    if not config.url:
        logger.info("Прокси не задан — прямое подключение к Telegram")
        return None, "direct"

    masked = mask_proxy_url(config.url)
    logger.info("Прокси: %s", masked)

    if config.check_on_start:
        logger.info("Проверка прокси (%s)...", config.check_url)
        ok, message = await check_proxy(config.url, config.check_url, config.timeout)
        if ok:
            logger.info("✓ %s", message)
        else:
            logger.error("✗ %s", message)
            logger.error("Проверку можно отключить: PROXY_CHECK=false")
            raise SystemExit(1)

    return create_bot_session(config.url), masked


async def _cli_check() -> int:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))

    config = load_proxy_config()
    if not config.url:
        print("PROXY не задан в .env — прямое подключение (прокси не нужен).")
        print("Пример: PROXY=socks5://127.0.0.1:1080")
        return 0

    print(f"Проверка: {mask_proxy_url(config.url)}")
    print(f"URL: {config.check_url}")

    ok, message = await check_proxy(config.url, config.check_url, config.timeout)
    if ok:
        print(f"OK: {message}")
        return 0

    print(f"FAIL: {message}")
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    raise SystemExit(asyncio.run(_cli_check()))
