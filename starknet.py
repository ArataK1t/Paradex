from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_py.constants import EC_ORDER  # Если такая константа доступна в вашей версии
from starknet_crypto_py import sign as rs_sign
import json

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


def flatten_signature(sig: list[str]) -> str: # <----  Убедитесь, что flatten_signature определена где-то в вашем коде!
    return f'["{sig[0]}","{sig[1]}"]'

def encode_str_to_felt(text: str) -> int:
    """Преобразует короткую строку в число (felt)."""
    result = 0
    for c in text:
        result = result * 256 + ord(c)
    return result

def generate_starknet_order_signature(order_params: dict, private_key_hex: str, paradex_config: dict, account_address: str) -> str:
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
    
    # Преобразуем строковые поля в felt
    market_felt = encode_str_to_felt(order_params['market'])
    side_felt = encode_str_to_felt(order_params['side'])
    order_type_felt = encode_str_to_felt(order_params['type'])
    
    # Формируем сообщение для подписи.
    # Для MARKET ордеров поле price исключается.
    order_message = {
        "timestamp": order_params['signature_timestamp'],  # число (в миллисекундах)
        "market": market_felt,
        "side": side_felt,
        "orderType": order_type_felt,
        "size": int(float(order_params['size']))
    }
    if order_params['type'] not in ("MARKET", "STOP_MARKET", "STOP_LOSS_MARKET", "TAKE_PROFIT_MARKET"):
        order_message["price"] = int(float(order_params.get('price', 0)))
    
    # Формируем домен. Важно также преобразовать строковые поля домена в felt.
    domain = {
        "name": encode_str_to_felt("Paradex"),
        "chainId": chain_id,  # уже число
        "version": encode_str_to_felt("1")
    }
    
    # Определяем тип Order – для MARKET ордеров поле price не включается.
    order_fields = [
        {"name": "timestamp", "type": "felt"},
        {"name": "market", "type": "felt"},
        {"name": "side", "type": "felt"},
        {"name": "orderType", "type": "felt"},
        {"name": "size", "type": "felt"}
    ]
    if order_params['type'] not in ("MARKET", "STOP_MARKET", "STOP_LOSS_MARKET", "TAKE_PROFIT_MARKET"):
        order_fields.append({"name": "price", "type": "felt"})
    
    order_msg = {
        "domain": domain,
        "primaryType": "Order",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"}
            ],
            "Order": order_fields
        },
        "message": order_message,
    }
    
    print(f"TypedData для ордера (JSON):\n{json.dumps(order_msg, indent=2)}")
    
    typed_data = TypedData.from_dict(order_msg)
    # Используем account_address (преобразованный в int) для вычисления хеша
    msg_hash = typed_data.message_hash(int(account_address, 16))
    print(f"Message Hash для ордера: {msg_hash}")
    
    r, s = message_signature(msg_hash, int(private_key_hex, 16))
    sig = [str(r), str(s)]
    signature_str = flatten_signature(sig)
    return signature_str
