#!/usr/bin/env python3
from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_py.constants import EC_ORDER
from starknet_crypto_py import sign as rs_sign
from starknet_py.cairo.felt import encode_shortstring

def str_to_felt(s: str) -> int:
    """
    Преобразует короткую строку в felt.
    Обратите внимание: строка должна быть не длиннее ~31 символа.
    """
    return int(encode_shortstring(s))

def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    import random
    k = random.randint(1, EC_ORDER - 1)
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k)

def generate_starknet_auth_signature(
    account_address: str,
    timestamp: int,
    expiration: int,
    private_key_hex: str,
    paradex_config: dict
) -> list[str]:
    """
    Генерирует подпись для аутентификации в соответствии с документацией Paradex.
    
    Параметры:
      - account_address: адрес аккаунта в hex-формате.
      - timestamp, expiration: метки времени для сообщения.
      - private_key_hex: приватный ключ (для StarkNet) в hex-формате.
      - paradex_config: конфигурация с параметром "starknet_chain_id".
    """
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
    
    # Формируем сообщение для подписи.
    # Поля, объявленные как felt, должны быть числами.
    auth_msg = {
        "message": {
            "method": str_to_felt("POST"),
            "path": str_to_felt("/v1/auth"),
            # Пустое тело передаём как 0
            "body": 0,
            "timestamp": timestamp,
            "expiration": expiration,
        },
        "domain": {
            "name": str_to_felt("Paradex"),
            "chainId": chain_id,
            "version": str_to_felt("1"),
        },
        "primaryType": "Request",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "Request": [
                {"name": "method", "type": "felt"},
                {"name": "path", "type": "felt"},
                {"name": "body", "type": "felt"},
                {"name": "timestamp", "type": "felt"},
                {"name": "expiration", "type": "felt"},
            ],
        },
    }
    
    typed_data = TypedData.from_dict(auth_msg)
    account_int = int(account_address, 16)
    msg_hash = typed_data.message_hash(account_int)
    
    priv_key = int(private_key_hex, 16)
    r, s = message_signature(msg_hash, priv_key)
    return [str(r), str(s)]

def generate_starknet_order_signature(
    order_params: dict,
    private_key_hex: str,
    paradex_config: dict
) -> list[str]:
    """
    Генерирует подпись для ордера согласно документации Paradex.
    
    order_params должен содержать следующие поля:
      - account_address: адрес аккаунта (hex-строка)
      - signature_timestamp: метка времени для подписи
      - market: название торговой пары (например, "BTC-USD-PERP")
      - side: "BUY" или "SELL" (для SHORT_HALF можно добавить дополнительную логику)
      - type: тип ордера (например, "MARKET")
      - size: размер ордера (число, если нужно, с плавающей точкой)
      - price: цена (число, если применимо, по умолчанию 0)
    """
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
    
    order_msg = {
        "domain": {
            "name": str_to_felt("Paradex"),
            "chainId": chain_id,
            "version": str_to_felt("1"),
        },
        "primaryType": "Order",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "Order": [
                {"name": "timestamp", "type": "felt"},
                {"name": "market", "type": "felt"},
                {"name": "side", "type": "felt"},
                {"name": "orderType", "type": "felt"},
                {"name": "size", "type": "felt"},
                {"name": "price", "type": "felt"},
            ],
        },
        "message": {
            "timestamp": int(order_params['signature_timestamp']),
            "market": str_to_felt(order_params['market']),
            # Для поля side: "1" для BUY, "2" для SELL.
            "side": str_to_felt("1") if order_params['side'] == "BUY" else str_to_felt("2"),
            "orderType": str_to_felt(order_params['type']),
            # Если order_params['size'] имеет дробную часть, приводим к float и затем к int.
            "size": int(float(order_params['size'])),
            "price": int(float(order_params.get('price', 0))),
        },
    }
    
    typed_data = TypedData.from_dict(order_msg)
    account_int = int(order_params['account_address'], 16)
    msg_hash = typed_data.message_hash(account_int)
    
    priv_key = int(private_key_hex, 16)
    r, s = message_signature(msg_hash, priv_key)
    return [str(r), str(s)]
