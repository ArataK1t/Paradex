from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_py.constants import EC_ORDER  # Если такая константа доступна в вашей версии
from starknet_crypto_py import generate_k_rfc6979, sign as rs_sign


# Предполагаем, что у вас есть функция message_signature, например:
def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    # Здесь можно использовать вашу реализацию, например, с использованием generate_k_rfc6979
    # и rs_sign из starknet_crypto_py
    from starknet_crypto_py import sign as rs_sign, generate_k_rfc6979
    k = generate_k_rfc6979(msg_hash, priv_key)
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k)

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
    order_params должен содержать (как минимум):
      - account_address: адрес аккаунта (hex-строка)
      - signature_timestamp: метка времени для подписи
      - market: название торговой пары (строка)
      - side: "BUY" или "SELL" (если нужно, можно добавить и обработку SHORT_HALF)
      - type: тип ордера (например, "MARKET")
      - size: размер ордера (число)
      - price: цена (число, если применимо, по умолчанию 0)
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
            "timestamp": int(order_params['signature_timestamp']),
            # При необходимости можно преобразовать строку в felt (например, используя encode_shortstring)
            "market": order_params['market'],
            # Преобразуем сторону в строковое представление: "1" для BUY, "2" для SELL
            "side": "1" if order_params['side'] == "BUY" else "2",
            "orderType": order_params['type'],
            "size": int(order_params['size']),
            "price": int(order_params.get('price', 0)),
        },
    }
    
    typed_data = TypedData.from_dict(order_msg)
    account_int = int(order_params['account_address'], 16)
    msg_hash = typed_data.message_hash(account_int)
    
    priv_key = int(private_key_hex, 16)
    r, s = message_signature(msg_hash, priv_key)
    return [str(r), str(s)]
