#!/usr/bin/env python3
import aiohttp
import asyncio
import json
import time
import random
import os
import logging
from typing import Dict, Tuple, List

# --- Импорт функций StarkNet подписи из файлов helpers (скопируйте их в ту же директорию) ---
from helpers.account import Account
from helpers.auth import build_auth_message, build_order_message
from utils import get_chain_id, hex_to_int
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_crypto_py import sign as rs_sign
from starknet_py.constants import EC_ORDER


# --- Конфигурация и Данные ---
CONFIG_FILE = "config.json"
WALLET_FILE = "wallets.json"
PROXY_FILE = "proxies.txt"
USER_AGENT_FILE = "user_agents.txt"  # Файл с User-Agent

paradex_http_url = "https://api.testnet.paradex.trade/v1" # URL API Paradex

# --- Загрузка данных из файлов ---
def load_config():
    """Загружает конфигурацию из JSON файла."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            required_params = [
                "trading_pair",
                "balance_usage_percentage",
                "leverage",
                "delay_between_cycles_seconds",
                "delay_between_trades_seconds",
                "delay_between_buy_sell_seconds",
                "delay_between_groups_seconds",
                "cycles_per_account"
            ]
            for param in required_params:
                if param not in config:
                    print(f"Ошибка конфигурации: Параметр '{param}' не найден в config.json")
                    return None
            return config
    except FileNotFoundError:
        print(f"Ошибка: Файл конфигурации '{CONFIG_FILE}' не найден.")
        return None
    except json.JSONDecodeError:
        print(f"Ошибка: Файл конфигурации '{CONFIG_FILE}' содержит некорректный JSON.")
        return None

def load_wallets():
    """Загружает данные кошельков из JSON файла."""
    try:
        with open(WALLET_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Ошибка: Файл кошельков '{WALLET_FILE}' не найден.")
        return None

def load_proxies():
    """Загружает прокси из текстового файла."""
    try:
        with open(PROXY_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
            return proxies
    except FileNotFoundError:
        print(f"Ошибка: Файл прокси '{PROXY_FILE}' не найден.")
        return []

def load_user_agents():
    """Загружает User-Agent из текстового файла."""
    try:
        with open(USER_AGENT_FILE, 'r') as f:
            user_agents = [line.strip() for line in f if line.strip()]
            return user_agents
    except FileNotFoundError:
        print(f"Ошибка: Файл User-Agent '{USER_AGENT_FILE}' не найден.")
        return []

async def get_paradex_config_from_api():
    """Загружает конфигурацию Paradex API."""
    url = paradex_http_url + '/system/config'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print(f"Запрос config, статус ответа: {response.status}")
            try:
                response.raise_for_status()
            except aiohttp.ClientResponseError as e:
                print(f"Ошибка при загрузке paradex_config: HTTP статус {response.status}, текст ошибки: {e}")
                return None
            except Exception as e:
                print(f"Непредвиденная ошибка при загрузке paradex_config: {e}")
                return None
            return await response.json()

# --- Асинхронные функции для API Paradex (с повторными попытками), ИСПОЛЬЗУЮТ HELPERS ФАЙЛЫ ДЛЯ ПОДПИСИ ---
async def get_jwt_token(session, account_data, paradex_config):
    api_url = paradex_http_url + "/auth"
    chain_id_int = get_chain_id(paradex_config["starknet_chain_id"])
    account = Account( # Используем класс Account из helpers/account.py
        client=FullNodeClient(node_url=paradex_config["starknet_fullnode_rpc_url"]),
        address=account_data['address'],
        key_pair=KeyPair.from_private_key(key=hex_to_int(account_data['private_key'])),
        chain=chain_id_int,
    )

    now = int(time.time())
    expiry = now + 1800
    message = build_auth_message(chain_id_int.value, now, expiry) # Используем build_auth_message из helpers/auth.py
    sig = account.sign_message(message) # Используем Account.sign_message для подписи

    headers: Dict = {
        "PARADEX-STARKNET-ACCOUNT": account_data['address'],
        "PARADEX-STARKNET-SIGNATURE": f'["{sig[0]}","{sig[1]}"]', # Формат подписи как в примере GitHub
        "PARADEX-TIMESTAMP": str(now),
        "PARADEX-SIGNATURE-EXPIRATION": str(expiry),
    }

    retry_delay_seconds = 5
    while True:
        try:
            async with session.post(api_url, headers=headers, proxy=account_data['proxy']) as response:
                print(f"Аккаунт {account_data['account_index']}: Запрос JWT, статус ответа: {response.status}")
                response.raise_for_status()
                raw_response_text = await response.text()
                print(f"Аккаунт {account_data['account_index']}: Raw JWT Response Text: {raw_response_text}")
                jwt_response_json = await response.json()
                print(f"Аккаунт {account_data['account_index']}: Parsed JWT Response JSON: {jwt_response_json}")
                jwt_token = jwt_response_json.get('jwt_token')
                if jwt_token:
                    print(f"Аккаунт {account_data['account_index']}: JWT токен успешно получен.")
                    return jwt_token
                else:
                    print(f"Аккаунт {account_data['account_index']}: Ошибка получения JWT токена, токен не найден. Ответ API: {jwt_response_json}")
        except aiohttp.ClientError as e:
            print(f"Аккаунт {account_data['account_index']}: Ошибка API при запросе JWT токена: {e}. Повторная попытка через {retry_delay_seconds} секунд...")
        except Exception as e:
            print(f"Аккаунт {account_data['account_index']}: Непредвиденная ошибка при обработке ответа JWT токена: {e}. Повторная попытка через {retry_delay_seconds} секунд...")
        await asyncio.sleep(retry_delay_seconds)


async def get_account_info(session, jwt_token, proxy):
    """Получает информацию об аккаунте с повторными попытками."""
    api_url = paradex_http_url + "/account"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {jwt_token}'
    }
    retry_delay_seconds = 5
    while True:
        try:
            async with session.get(api_url, headers=headers, proxy=proxy) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Ошибка получения информации об аккаунте: {e}. Повторная попытка через {retry_delay_seconds} секунд...")
        except Exception as e:
            print(f"Непредвиденная ошибка при получении информации об аккаунте: {e}. Повторная попытка через {retry_delay_seconds} секунд...")
        await asyncio.sleep(retry_delay_seconds)

async def place_order(session, jwt_token, order_params, private_key, proxy, paradex_config, account_data):
    """Размещает ордер с повторными попытками."""
    api_url = paradex_http_url + "/orders"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {jwt_token}'
    }
    order_params['signature_timestamp'] = int(time.time())
    order_params['account_address'] = account_data['address']

    chain_id_int = get_chain_id(paradex_config["starknet_chain_id"]) # Получаем chainId как IntEnum
    account = Account( # Создаем экземпляр Account для подписи
        client=FullNodeClient(node_url=paradex_config["starknet_fullnode_rpc_url"]),
        address=account_data['address'],
        key_pair=KeyPair.from_private_key(key=hex_to_int(account_data['private_key'])),
        chain=chain_id_int,
    )
    message = build_order_message(chain_id_int.value, order_params) # Используем build_order_message из helpers/auth.py
    sig = account.sign_message(message) # Подписываем ордер, используя Account.sign_message
    order_params['signature'] = [str(sig[0]), str(sig[1])] # Формат подписи как в примере GitHub


    retry_delay_seconds = 5
    while True:
        try:
            async with session.post(api_url, headers=headers, json=order_params, proxy=proxy) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Ошибка размещения ордера: {e}, Параметры: {order_params}. Повторная попытка через {retry_delay_seconds} секунд...")
        except Exception as e:
            print(f"Непредвиденная ошибка при размещении ордера: {e}. Параметры: {order_params}. Повторная попытка через {retry_delay_seconds} секунд...")
        await asyncio.sleep(retry_delay_seconds)

async def get_open_positions(session, jwt_token, proxy):
    """Получает список открытых позиций с повторными попытками."""
    api_url = paradex_http_url + "/positions"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {jwt_token}'
    }
    retry_delay_seconds = 5
    while True:
        try:
            async with session.get(api_url, headers=headers, proxy=proxy) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Ошибка получения открытых позиций: {e}. Повторная попытка через {retry_delay_seconds} секунд...")
        except Exception as e:
            print(f"Непредвиденная ошибка при получении открытых позиций: {e}. Повторная попытка через {retry_delay_seconds} секунд...")
        await asyncio.sleep(retry_delay_seconds)

async def close_positions(session, jwt_token, market, positions, private_key, proxy, paradex_config, config, account_data): # Добавили account_data для place_order
    """Закрывает открытые позиции на рынке с повторными попытками."""
    closed_orders = []
    for position in positions.get('results', []):
        if position['market'] == market:
            side_to_close = "BUY" if position['side'] == "SHORT" else "SELL"
            close_order_params = {
                "market": market,
                "side": side_to_close,
                "type": "MARKET",
                "size": position['size'],
                "instruction": "GTC",
                "leverage": config['leverage']
            }
            order_response = await place_order(session, jwt_token, close_order_params, private_key, proxy, paradex_config, account_data) # Передаем account_data
            if order_response:
                closed_orders.append(order_response)
            else:
                print(f"Не удалось разместить ордер на закрытие позиции: {position}")
    return closed_orders

# --- Основная логика работы бота ---
async def trade_cycle(account_data, config, paradex_config):
    """Торговый цикл для одного аккаунта."""
    print(f"Начинаем торговый цикл для аккаунта: {account_data['address']}")
    default_headers = {
        'User-Agent': account_data['user_agent'] if account_data['user_agent'] else 'ParadexBot-Default-UA'
    }
    session = aiohttp.ClientSession(headers=default_headers)
    try:
        jwt_token = await get_jwt_token(session, account_data, paradex_config)
        if not jwt_token:
            print(f"Пропускаем аккаунт {account_data['address']} из-за ошибки аутентификации.")
            return
        account_info = await get_account_info(session, jwt_token, account_data['proxy'])
        if not account_info:
            print(f"Пропускаем аккаунт {account_data['address']} из-за ошибки получения информации об аккаунте.")
            return
        if account_info.get('status') != 'ACTIVE':
            print(f"Аккаунт {account_data['address']} не активен. Статус: {account_info.get('status')}. Пропускаем.")
            return
        free_collateral = float(account_info.get('free_collateral', 0))
        if free_collateral <= 0:
            print(f"Аккаунт {account_data['address']} имеет недостаточно free collateral ({free_collateral}). Пропускаем.")
            return

        # --- Расчет размера позиции ---
        balance_usage_percentage_min, balance_usage_percentage_max = config['balance_usage_percentage']
        balance_usage_percent = random.uniform(balance_usage_percentage_min, balance_usage_percentage_max) / 100.0
        position_size_usd = free_collateral * balance_usage_percent
        print(f"Аккаунт {account_data['address']}: Free collateral = {free_collateral}, Размер позиции (USD) = {position_size_usd:.2f}")

        # --- Размещение ордеров (Лонг/Шорт) ---
        order_side = account_data['order_side']
        order_size = str(position_size_usd)
        if order_side == "SHORT_HALF":
            order_size = str(position_size_usd / 2.0)

        order_params = {
            "market": config['trading_pair'],
            "side": order_side if order_side != "SHORT_HALF" else "SELL",
            "type": "MARKET",
            "size": order_size,
            "instruction": "GTC",
            "leverage": config['leverage']
        }

        order_response = await place_order(session, jwt_token, order_params, account_data['private_key'], account_data['proxy'], paradex_config, account_data)
        if order_response:
            print(f"Аккаунт {account_data['address']} разместил {order_side} ордер. Ответ: {order_response}")
        else:
            print(f"Аккаунт {account_data['address']} НЕ смог разместить {order_side} ордер. Ошибка.")

        # --- Задержка между операциями ---
        if order_side in ["BUY", "SELL", "SHORT_HALF"]:
            delay_buy_sell_seconds_min, delay_buy_sell_seconds_max = config['delay_between_buy_sell_seconds']
            delay_buy_sell_seconds = random.uniform(delay_buy_sell_seconds_min, delay_buy_sell_seconds_max)
            print(f"Аккаунт {account_data['address']}: Ждем {delay_buy_sell_seconds:.2f} секунд после {order_side} ордера...")
            await asyncio.sleep(delay_buy_sell_seconds)

        delay_seconds_min, delay_seconds_max = config['delay_between_trades_seconds']
        delay_seconds = random.uniform(delay_seconds_min, delay_seconds_max)
        print(f"Аккаунт {account_data['address']}: Ждем {delay_seconds:.2f} секунд перед закрытием позиций...")
        await asyncio.sleep(delay_seconds)

        open_positions = await get_open_positions(session, jwt_token, account_data['proxy'])
        if open_positions:
            closed_orders = await close_positions(session, jwt_token, config['trading_pair'], open_positions, account_data['private_key'], account_data['proxy'], paradex_config, config, account_data) # Передаем account_data
            print(f"Аккаунт {account_data['address']}: Закрыто {len(closed_orders)} позиций. Ответы: {closed_orders}")
        else:
            print(f"Аккаунт {account_data['address']}: Не удалось получить список открытых позиций для закрытия.")

        cycle_delay_seconds_min, cycle_delay_seconds_max = config['delay_between_cycles_seconds']
        cycle_delay_seconds = random.uniform(cycle_delay_seconds_min, cycle_delay_seconds_max)
        print(f"Аккаунт {account_data['address']}: Ждем {cycle_delay_seconds:.2f} секунд перед следующим циклом...")
        await asyncio.sleep(cycle_delay_seconds)

    except Exception as e:
        print(f"!!! Общая ошибка в торговом цикле для аккаунта {account_data['address']}: {e}")
    finally:
        await session.close()
        print(f"Торговый цикл для аккаунта {account_data['address']} завершен.\n")


# --- Основная функция бота ---
async def main():
    config = load_config()
    if not config:
        return

    wallets = load_wallets()
    if not wallets:
        print("Ошибка: Файл wallets.json не загружен или пуст.")
        return

    proxies = load_proxies()
    if not proxies:
        print("Ошибка: Файл proxies.txt не загружен или пуст, работа БЕЗ ПРОКСИ невозможна. Бот остановлен.")
        return

    user_agents = load_user_agents()
    if not user_agents:
        print("Предупреждение: Файл user_agents.txt не загружен или пуст. Будет использоваться User-Agent по умолчанию.")

    if len(wallets) < 2:
        print("Ошибка: Для работы стратегии необходимо минимум 2 аккаунта. Бот остановлен.")
        return

    if len(wallets) != len(proxies):
        print(f"Ошибка: Количество кошельков ({len(wallets)}) не соответствует количеству прокси ({len(proxies)}). Бот остановлен.")
        return

    paradex_config = await get_paradex_config_from_api() # Используем функцию для загрузки конфига
    if not paradex_config:
        print("Не удалось загрузить конфигурацию Paradex.")
        return

    # Связывание кошельков, прокси и User-Agent (1 к 1)
    account_data_list = []
    num_user_agents = len(user_agents)
    for i in range(len(wallets)):
        wallet = wallets[i]
        proxy = proxies[i]
        user_agent = user_agents[i % num_user_agents] if user_agents else None
        account_data = {
            'address': wallet['address'],
            'private_key': wallet['private_key'],
            'proxy': proxy,
            'user_agent': user_agent,
            'account_index': i,
            'order_side': None
        }
        account_data_list.append(account_data)

    cycles_per_account_min, cycles_per_account_max = config['cycles_per_account']
    cycles_per_account = random.randint(cycles_per_account_min, cycles_per_account_max)
    print(f"Бот будет работать {cycles_per_account} циклов на аккаунт.")

    delay_between_groups_seconds_min, delay_between_groups_seconds_max = config['delay_between_groups_seconds']
    for cycle_number in range(cycles_per_account):
        print(f"\n--- Начало цикла #{cycle_number + 1} ---")
        random.shuffle(account_data_list)
        account_groups = []
        account_index = 0
        num_accounts = len(account_data_list)
        num_triplets = num_accounts // 3
        remainder = num_accounts % 3
        num_pairs = 0
        if remainder == 1:
            num_triplets -= 1
            num_pairs += 2
        elif remainder == 2:
            num_pairs += 1
        print(f"Формируем {num_triplets} групп по 3 аккаунта и {num_pairs} групп по 2 аккаунта.")
        for _ in range(num_triplets):
            group = account_data_list[account_index:account_index + 3]
            account_groups.append(group)
            account_index += 3
            print(f"  Группа размера: {len(group)}")
        for _ in range(num_pairs):
            group = account_data_list[account_index:account_index + 2]
            account_groups.append(group)
            account_index += 2
            print(f"  Группа размера: {len(group)}")
        print(f"Сформировано групп: {len(account_groups)}")
        for group_index, group in enumerate(account_groups):
            print(f"\n-- Обработка группы #{group_index + 1} (размер: {len(group)}) --")
            if len(group) == 2:
                group[0]['order_side'] = "BUY"
                group[1]['order_side'] = "SELL"
            elif len(group) == 3:
                group[0]['order_side'] = "BUY"
                group[1]['order_side'] = "SELL"
                group[2]['order_side'] = "SHORT_HALF"
            else:
                print("Ошибка: Некорректный размер группы!")
                continue
            tasks = []
            for account_data in group:
                if account_data['order_side'] is not None:
                    tasks.append(trade_cycle(account_data, config, paradex_config))
            await asyncio.gather(*tasks)
            print(f"-- Группа #{group_index + 1} отработана. Завершение обработки группы. --")
            delay_between_groups_seconds = random.uniform(delay_between_groups_seconds_min, delay_between_groups_seconds_max)
            print(f"Ждем {delay_between_groups_seconds:.2f} секунд перед началом обработки следующей группы...")
            await asyncio.sleep(delay_between_groups_seconds)
        print(f"\n--- Цикл #{cycle_number + 1} завершен для всех групп. ---\n")
    print("Все торговые циклы завершены.")

if __name__ == "__main__":
    # Logging setup (optional, but good for debugging)
    logging.basicConfig(
        level=os.getenv("LOGGING_LEVEL", "INFO"), # Можно установить уровень логирования через переменную окружения LOGGING_LEVEL, например DEBUG, INFO, WARNING, ERROR, CRITICAL
        format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(main())