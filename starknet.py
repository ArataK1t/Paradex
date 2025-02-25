from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_py.constants import EC_ORDER  # Если такая константа доступна в вашей версии
from starknet_crypto_py import sign as rs_sign

def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    import random # Импортируем random здесь, если еще не импортирован
    k = random.randint(1, EC_ORDER - 1) # <---- Генерируем случайное k
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k) # <---- Передаем k


def generate_starknet_auth_signature(account_address: str, timestamp: int, expiration: int, private_key_hex: str, paradex_config: dict) -> list[str]:
    """
    Генерирует подпись для аутентификации в соответствии с документацией Paradex.
    Параметры:
      - account_address: адрес аккаунта в hex-формате
      - timestamp, expiration: метки времени для сообщения
      - private_key_hex: приватный ключ (уже выведенный для StarkNet) в hex-формате
      - paradex_config: конфигурация с параметром "starknet_chain_id"
    """
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
    
    # Формирование сообщения (схема как в build_auth_message из доков)
    auth_msg = {
        "message": {
            "method": "POST",
            "path": "/v1/auth",
            "body": "",
            "timestamp": timestamp,
            "expiration": expiration,
        },
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
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
    
    # Создаём объект TypedData из сообщения
    typed_data = TypedData.from_dict(auth_msg)
    # Преобразуем адрес аккаунта в int (если передан в виде hex-строки)
    account_int = int(account_address, 16)
    msg_hash = typed_data.message_hash(account_int)
    
    priv_key = int(private_key_hex, 16)
    r, s = message_signature(msg_hash, priv_key)
    return [str(r), str(s)]


def generate_starknet_order_signature(order_params: dict, private_key_hex: str, paradex_config: dict) -> list[str]:
    """
    Генерирует подпись для ордера согласно документации Paradex.
    """
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())

    order_msg = {
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
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
            "timestamp": int(order_params['signature_timestamp']),  # 🟢 Приведение к int
            "market": int.from_bytes(order_params['market'].encode(), "big"),  # 🟢 Преобразуем строку в felt
            "side": 1 if order_params['side'] == "BUY" else 2,  # 🟢 Приведение к числу
            "orderType": int.from_bytes(order_params['type'].encode(), "big"),  # 🟢 Преобразуем строку в felt
            "size": int(float(order_params['size'])),  # 🟢 Приведение к int
            "price": int(float(order_params.get('price', 0))),  # 🟢 Приведение к int
        },
    }

    typed_data = TypedData.from_dict(order_msg)
    account_int = int(order_params['account_address'], 16)
    msg_hash = typed_data.message_hash(account_int)

    priv_key = int(private_key_hex, 16)
    r, s = message_signature(msg_hash, priv_key)
    return [str(r), str(s)]
