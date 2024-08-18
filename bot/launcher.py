import asyncio
import random
from argparse import ArgumentParser
from itertools import cycle
from pathlib import Path
from typing import NamedTuple

from better_proxy import Proxy
from pyrogram import Client

from bot.config.logger import log
from bot.config.settings import config, logo
from bot.core.bot import run_bot
from bot.utils import get_session_profiles

start_text = """
    Select an action:
        1. Create session
        2. Run bot
    """


class SessionData(NamedTuple):
    tg_client: Client
    session_data: dict


def get_session_names() -> list[str]:
    # 按照session文件名的数值部分排序
    return sorted(
        [file.stem for file in Path("sessions").glob("*.session")],
        key=lambda name: int(name)  # 假设文件名为纯数字，比如 1.session
    )


def get_proxies() -> list[str | None]:
    if config.USE_PROXY_FROM_FILE:
        with Path("proxies.txt").open(encoding="utf-8") as file:
            proxies = []
            for row in file:
                proxy = row.strip()
                try:
                    # 提取IP地址和端口号部分
                    ip_port = proxy.split('@')[-1]
                    ip, port = ip_port.split(':')
                    port = int(port)  # 确保端口是整数
                    proxies.append(Proxy.from_str(proxy=proxy).as_url)
                except (ValueError, IndexError) as e:
                    log.warning(f"Invalid proxy format detected and skipped: {proxy} - {str(e)}")
            return proxies
    return None


async def get_tg_clients() -> list[SessionData]:
    session_names = get_session_names()

    if not session_names:
        msg = "Not found session files"
        raise FileNotFoundError(msg)
    session_profiles = get_session_profiles(session_names)
    return [
        SessionData(
            tg_client=Client(
                name=session_name,
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                workdir="sessions/",
            ),
            session_data=session_profiles[session_name],
        )
        for session_name in session_names
    ]


async def run_bot_with_delay(tg_client: Client, proxy: str | None, additional_data: dict) -> None:
    delay = random.randint(*config.SLEEP_BETWEEN_START)
    bound_logger = log.bind(session_name=tg_client.name, proxy=str(proxy))
    bound_logger.info(f"Wait {delay} seconds before start with proxy: {proxy}")
    await asyncio.sleep(delay)
    await run_bot(tg_client=tg_client, proxy=proxy, additional_data=additional_data)


async def run_clients(session_data: list[SessionData]) -> None:
    proxies = get_proxies()
    
    if not proxies:
        log.error("No proxies found. Exiting.")
        return
    
    if len(proxies) < len(session_data):
        log.error("Not enough proxies for all sessions. Exiting.")
        return
    
    # 逐一绑定session与代理
    tasks = []
    for i, s_data in enumerate(session_data):
        proxy = proxies[i]
        tasks.append(run_bot_with_delay(tg_client=s_data.tg_client, proxy=proxy, additional_data=s_data.session_data))
    
    await asyncio.gather(*tasks)


async def start() -> None:
    print(logo)
    parser = ArgumentParser()
    parser.add_argument("-a", "--action", type=int, choices=[1, 2], help="Action to perform  (1 or 2)")
    log.info(f"Detected {len(get_session_names())} sessions | {len(proxy) if (proxy := get_proxies()) else 0} proxies")
    action = parser.parse_args().action

    if not action:
        print(start_text)
        while True:
            action = input("> ").strip()
            if action.isdigit() and action in ["1", "2"]:
                action = int(action)
                break
            log.warning("Action must be a number (1 or 2)")

    if action == 1:
        await register_sessions()
    elif action == 2:
        session_data = await get_tg_clients()
        await run_clients(session_data=session_data)
