#!/usr/bin/env python3
import aiohttp
import asyncio
import json
import time
import random

from starknet import generate_starknet_auth_signature, generate_starknet_order_signature

CONFIG_FILE = "config.json"
WALLET_FILE = "wallets.json"
PROXY_FILE = "proxies.txt"
USER_AGENT_FILE = "user_agents.txt"

def load_config():
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
    try:
        with open(WALLET_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Ошибка: Файл кошельков '{WALLET_FILE}' не найден.")
        return None

def load_proxies():
    try:
        with open(PROXY_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Ошибка: Файл прокси '{PROXY_FILE}' не найден.")
        return []

def load_user_agents():
    try:
        with open(USER_AGENT_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Ошибка: Файл User-Agent '{USER_AGENT_FILE}' не найден.")
        return []

async def get_jwt_token(session, account_data, paradex_config):
    api_url = "https://api.testnet.paradex.trade/v1/auth"
    current_time = int(time.time())
    expiration_time = current_time + 1800
    headers = {
        'Accept': 'application/json',
        'PARADEX-STARKNET-ACCOUNT': account_data['address'],
        'PARADEX-TIMESTAMP': str(current_time),
        'PARADEX-SIGNATURE-EXPIRATION': str(expiration_time)
    }
    signature_parts = generate_starknet_auth_signature(
        account_data['address'],
        current_time,
        expiration_time,
        account_data['private_key'],
        paradex_config
    )
    headers['PARADEX-STARKNET-SIGNATURE'] = json.dumps(signature_parts)
    
    retry_delay = 5
    while True:
        try:
            async with session.post(api_url, headers=headers, proxy=account_data['proxy']) as response:
                print(f"Аккаунт {account_data['account_index']}: Запрос JWT, статус ответа: {response.status}")
                response.raise_for_status()
                raw_text = await response.text()
                print(f"Аккаунт {account_data['account_index']}: Raw JWT Response Text: {raw_text}")
                data = await response.json()
                print(f"Аккаунт {account_data['account_index']}: Parsed JWT Response JSON: {data}")
                jwt_token = data.get("jwt_token")
                if jwt_token:
                    print(f"Аккаунт {account_data['account_index']}: JWT токен успешно получен.")
                    return jwt_token
                else:
                    print(f"Аккаунт {account_data['account_index']}: Ошибка получения JWT: токен не найден.")
        except Exception as e:
            print(f"Аккаунт {account_data['account_index']}: Ошибка при запросе JWT: {e}. Повтор через {retry_delay} секунд.")
        await asyncio.sleep(retry_delay)

async def get_account_info(session, jwt_token, proxy):
    api_url = "https://api.testnet.paradex.trade/v1/account"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {jwt_token}'
    }
    retry_delay = 5
    while True:
        try:
            async with session.get(api_url, headers=headers, proxy=proxy) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            print(f"Ошибка получения информации об аккаунте: {e}. Повтор через {retry_delay} секунд.")
        await asyncio.sleep(retry_delay)

async def place_order(session, jwt_token, order_params, private_key, proxy, paradex_config, account_data):
    api_url = "https://api.testnet.paradex.trade/v1/orders"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {jwt_token}'
    }
    # Используем миллисекунды для signature_timestamp
    order_params['signature_timestamp'] = int(time.time() * 1000)
    if 'stp' not in order_params:
        order_params['stp'] = "EXPIRE_TAKER"
    print(f"Исходные параметры ордера до подписи: {json.dumps(order_params)}")
    # Генерация подписи
    order_params['signature'] = generate_starknet_order_signature(order_params, private_key, paradex_config, account_data['address'])
    
    # Формируем payload: удаляем лишние поля; для MARKET ордеров удаляем поле price.
    order_payload = {k: order_params[k] for k in order_params if k not in ("leverage", "account_address")}
    if order_payload.get("type") in ("MARKET", "STOP_MARKET", "STOP_LOSS_MARKET", "TAKE_PROFIT_MARKET"):
        order_payload.pop("price", None)
    print(f"Параметры ордера перед отправкой (JSON): {json.dumps(order_payload)}")
    
    retry_delay = 5
    while True:
        try:
            async with session.post(api_url, headers=headers, json=order_payload, proxy=proxy) as response:
                resp_text = await response.text()
                if response.status in (200, 201):
                    print(f"Ордер успешно создан. Статус: {response.status}. Ответ: {resp_text}")
                    return await response.json()
                else:
                    print(f"Ошибка размещения ордера: статус {response.status}. Ответ: {resp_text}. Параметры: {order_payload}")
                    response.raise_for_status()
        except Exception as e:
            print(f"Ошибка размещения ордера: {e}. Параметры: {order_payload}. Повтор через {retry_delay} секунд.")
        await asyncio.sleep(retry_delay)

async def get_open_positions(session, jwt_token, proxy):
    api_url = "https://api.testnet.paradex.trade/v1/positions"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {jwt_token}'
    }
    retry_delay = 5
    while True:
        try:
            async with session.get(api_url, headers=headers, proxy=proxy) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            print(f"Ошибка получения открытых позиций: {e}. Повтор через {retry_delay} секунд.")
        await asyncio.sleep(retry_delay)

async def close_positions(session, jwt_token, market, positions, private_key, proxy, paradex_config, config, account_data):
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
                "stp": "EXPIRE_TAKER"
            }
            order_response = await place_order(session, jwt_token, close_order_params, private_key, proxy, paradex_config, account_data)
            if order_response:
                closed_orders.append(order_response)
            else:
                print(f"Не удалось разместить ордер на закрытие позиции: {position}")
    return closed_orders

async def trade_cycle(account_data, config, paradex_config):
    print(f"Начинаем торговый цикл для аккаунта: {account_data['address']}")
    default_headers = {
        'User-Agent': account_data['user_agent'] if account_data['user_agent'] else 'ParadexBot-Default-UA'
    }
    session = aiohttp.ClientSession(headers=default_headers)
    try:
        jwt_token = await get_jwt_token(session, account_data, paradex_config)
        if not jwt_token:
            print(f"Аккаунт {account_data['address']}: Пропуск из-за отсутствия JWT.")
            return
        account_info = await get_account_info(session, jwt_token, account_data['proxy'])
        if not account_info:
            print(f"Аккаунт {account_data['address']}: Пропуск из-за отсутствия информации об аккаунте.")
            return
        if account_info.get('status') != 'ACTIVE':
            print(f"Аккаунт {account_data['address']}: не активен (статус: {account_info.get('status')}). Пропуск.")
            return
        free_collateral = float(account_info.get('free_collateral', 0))
        if free_collateral <= 0:
            print(f"Аккаунт {account_data['address']}: Недостаточно free collateral ({free_collateral}). Пропуск.")
            return

        balance_usage_min, balance_usage_max = config['balance_usage_percentage']
        balance_percent = random.uniform(balance_usage_min, balance_usage_max) / 100.0
        position_size_usd = free_collateral * balance_percent
        print(f"Аккаунт {account_data['address']}: Free collateral = {free_collateral}, Размер позиции = {position_size_usd:.2f} USD")

        order_side = account_data['order_side']
        order_size = str(int(position_size_usd))
        if order_side == "SHORT_HALF":
            order_size = str(int(position_size_usd / 2.0))

        order_params = {
            "market": config['trading_pair'],
            "side": order_side if order_side != "SHORT_HALF" else "SELL",
            "type": "MARKET",
            "size": order_size,
            "instruction": "GTC",
            "stp": "EXPIRE_TAKER"
        }
        print(f"Аккаунт {account_data['address']} - параметры ордера до подписи: {json.dumps(order_params)}")
        order_response = await place_order(session, jwt_token, order_params, account_data['private_key'], account_data['proxy'], paradex_config, account_data)
        if order_response:
            print(f"Аккаунт {account_data['address']}: Ордер размещён ({order_side}). Ответ: {order_response}")
        else:
            print(f"Аккаунт {account_data['address']}: Не удалось разместить ордер ({order_side}).")

        if order_side in ["BUY", "SELL", "SHORT_HALF"]:
            delay_buy_sell_min, delay_buy_sell_max = config['delay_between_buy_sell_seconds']
            delay_buy_sell = random.uniform(delay_buy_sell_min, delay_buy_sell_max)
            print(f"Аккаунт {account_data['address']}: Ждём {delay_buy_sell:.2f} секунд после ордера...")
            await asyncio.sleep(delay_buy_sell)

        delay_trades_min, delay_trades_max = config['delay_between_trades_seconds']
        delay_trades = random.uniform(delay_trades_min, delay_trades_max)
        print(f"Аккаунт {account_data['address']}: Ждём {delay_trades:.2f} секунд перед закрытием позиций...")
        await asyncio.sleep(delay_trades)

        open_positions = await get_open_positions(session, jwt_token, account_data['proxy'])
        if open_positions:
            closed_orders = await close_positions(session, jwt_token, config['trading_pair'], open_positions, account_data['private_key'], account_data['proxy'], paradex_config, config, account_data)
            print(f"Аккаунт {account_data['address']}: Закрыто {len(closed_orders)} позиций. Ответы: {closed_orders}")
        else:
            print(f"Аккаунт {account_data['address']}: Не удалось получить список открытых позиций.")

        delay_cycles_min, delay_cycles_max = config['delay_between_cycles_seconds']
        delay_cycles = random.uniform(delay_cycles_min, delay_cycles_max)
        print(f"Аккаунт {account_data['address']}: Ждём {delay_cycles:.2f} секунд перед следующим циклом...")
        await asyncio.sleep(delay_cycles)

    except Exception as e:
        print(f"Ошибка в торговом цикле для аккаунта {account_data['address']}: {e}")
    finally:
        await session.close()
        print(f"Торговый цикл для аккаунта {account_data['address']} завершён.\n")

async def get_paradex_config(paradex_http_url):
    url = paradex_http_url + '/system/config'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print(f"Запрос config, статус ответа: {response.status}")
            try:
                response.raise_for_status()
            except Exception as e:
                print(f"Ошибка загрузки paradex_config: {e}")
                return None
            return await response.json()

async def main():
    config = load_config()
    if not config:
        return

    wallets = load_wallets()
    if not wallets:
        print("Ошибка: wallets.json не загружен или пуст.")
        return

    proxies = load_proxies()
    if not proxies:
        print("Ошибка: proxies.txt не загружен или пуст, бот остановлен.")
        return

    user_agents = load_user_agents()
    if not user_agents:
        print("Предупреждение: user_agents.txt не загружен или пуст, будет использован User-Agent по умолчанию.")

    if len(wallets) < 2:
        print("Ошибка: для стратегии нужно минимум 2 аккаунта, бот остановлен.")
        return

    if len(wallets) != len(proxies):
        print(f"Ошибка: количество кошельков ({len(wallets)}) не соответствует количеству прокси ({len(proxies)}), бот остановлен.")
        return

    paradex_config = await get_paradex_config("https://api.testnet.paradex.trade/v1")
    if not paradex_config:
        print("Ошибка: не удалось загрузить конфигурацию Paradex.")
        return

    account_data_list = []
    num_user_agents = len(user_agents)
    for i, wallet in enumerate(wallets):
        account_data = {
            "address": wallet["address"],
            "private_key": wallet["private_key"],
            "proxy": proxies[i],
            "user_agent": user_agents[i % num_user_agents] if user_agents else None,
            "account_index": i,
            "order_side": None
        }
        account_data_list.append(account_data)

    cycles_min, cycles_max = config["cycles_per_account"]
    cycles = random.randint(cycles_min, cycles_max)
    print(f"Бот будет работать {cycles} циклов на аккаунт.")

    delay_groups_min, delay_groups_max = config["delay_between_groups_seconds"]
    for cycle_number in range(cycles):
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
            group = account_data_list[account_index:account_index+3]
            account_groups.append(group)
            account_index += 3
            print(f"  Группа размера: {len(group)}")
        for _ in range(num_pairs):
            group = account_data_list[account_index:account_index+2]
            account_groups.append(group)
            account_index += 2
            print(f"  Группа размера: {len(group)}")
        print(f"Сформировано групп: {len(account_groups)}")
        for group_index, group in enumerate(account_groups):
            print(f"\n-- Обработка группы #{group_index + 1} (размер: {len(group)}) --")
            if len(group) == 2:
                group[0]["order_side"] = "BUY"
                group[1]["order_side"] = "SELL"
            elif len(group) == 3:
                group[0]["order_side"] = "BUY"
                group[1]["order_side"] = "SELL"
                group[2]["order_side"] = "SHORT_HALF"
            else:
                print("Ошибка: Некорректный размер группы!")
                continue
            tasks = [trade_cycle(acc, config, paradex_config) for acc in group if acc["order_side"]]
            await asyncio.gather(*tasks)
            delay_groups = random.uniform(delay_groups_min, delay_groups_max)
            print(f"Ждём {delay_groups:.2f} секунд перед следующей группой...")
            await asyncio.sleep(delay_groups)
        print(f"\n--- Цикл #{cycle_number + 1} завершён для всех групп. ---\n")
    print("Все торговые циклы завершены.")

if __name__ == "__main__":
    asyncio.run(main())
