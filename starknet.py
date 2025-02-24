from starknet_py.net.signer.stark_curve_signer import KeyPair # Исправленный импорт для StarkCurveSigner
from starknet_py.hash import message_hash
from starknet_py.common import int_from_bytes
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.utils.typed_data import TypedData, DataEncoder
from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner
import time
import json

# --- StarkNet Подписи - РЕАЛИЗАЦИЯ ---
def generate_starknet_auth_signature(account_address, timestamp, expiration, private_key_hex, paradex_config):
    """Генерирует StarkNet подпись для аутентификации."""

    private_key = int(private_key_hex, 16) # Преобразуем HEX приватный ключ в int
    signer = KeyPair.from_private_key(private_key) # Используем KeyPair (исправлено)

    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode()) # Получаем chainId из конфига

    # --- StarkNet Domain Struct ---
    domain = {
        "name": "Paradex", # Тип "felt" (изменено)
        "version": "1", # Тип "felt" (изменено)
        "chainId": chain_id # Тип "felt" (остается)
    }

    # --- Message для подписи ---
    message = {
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"}, # Тип "felt" (изменено)
                {"name": "version", "type": "felt"}, # Тип "felt" (изменено)
                {"name": "chainId", "type": "felt"} # Тип "felt" (остается)
            ],
            "Auth": [
                {"name": "account", "type": "felt"},
                {"name": "timestamp", "type": "felt"},
                {"name": "expiration", "type": "felt"}
            ]
        },
        "primaryType": "Auth",
        "domain": domain,
        "message": {
            "account": int(account_address, 16), # Адрес аккаунта в int
            "timestamp": int(timestamp), # Timestamp в int
            "expiration": int(expiration) # Expiration в int
        }
    }

    # --- Вычисление хеша сообщения ---
    typed_data = TypedData.from_dict(message) # Создаем TypedData объект
    message_hash = DataEncoder.from_typed_data(typed_data).hash_message() # Хешируем сообщение - ИСПОЛЬЗУЕТСЯ message_hash (теперь импортируется из starknet_py.hash)

    # --- Подпись хеша сообщения ---
    signer_instance = StarkCurveSigner(account_address, private_key, chain_id) #  Создаем экземпляр StarkCurveSigner
    signature = signer_instance.sign(message_hash) # Подписываем хеш приватным ключом - исправлено, используем экземпляр

    return [str(signature.r), str(signature.s)] # Возвращаем подпись в виде массива строк


def generate_starknet_order_signature(order_params, private_key_hex, paradex_config):
    """Генерирует StarkNet подпись для ордера (ОБНОВЛЕННАЯ СТРУКТУРА на основе документации)."""
    private_key = int(private_key_hex, 16)
    signer_instance = StarkCurveSigner(order_params['account_address'], private_key, int_from_bytes(paradex_config["starknet_chain_id"].encode())) # исправлено
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())

    domain = { # Domain структура такая же, как и для аутентификации
        "name": "Paradex", # Тип "felt" (изменено)
        "version": "1", # Тип "felt" (изменено)
        "chainId": chain_id # Тип "felt" (остается)
    }

    # --- ОБНОВЛЕННАЯ структура Message для подписи ордера (на основе документации) ---
    message = {
        "types": {
            "StarkNetDomain": [ # StarkNetDomain - типы исправлены на "felt"
                {"name": "name", "type": "felt"}, # Тип "felt" (изменено)
                {"name": "version", "type": "felt"}, # Тип "felt" (изменено)
                {"name": "chainId", "type": "felt"} # Тип "felt" (остается)
            ],
            "Order": [ # Структура Order -  ОБНОВЛЕНА на основе документации
                {"name": "timestamp", "type": "felt"},  # Time of signature request; Acts as a nonce; (переименовано и тип "felt")
                {"name": "market", "type": "felt"},  # E.g.: "ETH-USD-PERP" (тип "felt")
                {"name": "side", "type": "felt"},  # Buy or Sell (тип "felt")
                {"name": "orderType", "type": "felt"},  # Limit or Market (переименовано и тип "felt")
                {"name": "size", "type": "felt"},  # Quantum value with 8 decimals; (тип "felt")
                {"name": "price", "type": "felt"},  # Quantum value with 8 decimals; Limit price or 0 (ДОБАВЛЕНО и тип "felt")
            ]
        },
        "primaryType": "Order", # Primary type теперь "Order"
        "domain": domain,
        "message": { # message - параметры ордера из order_params - ОБНОВЛЕНО
            "timestamp": int(order_params['signature_timestamp']), # timestamp (переименовано)
            "market": order_params['market'].encode(), # market (тип bytes для felt)
            "side":  b'\x01' if order_params['side'] == "BUY" else b'\x02', # side (конвертация в 1 или 2, тип bytes для felt)
            "orderType": order_params['type'].encode(), # orderType (переименовано, тип bytes для felt)
            "size": int(order_params['size']), # size (остается int)
            "price": int(order_params.get('price', 0)), # price (ДОБАВЛЕНО, берем из order_params или 0, int)
        }
    }

    typed_data = TypedData.from_dict(message)
    message_hash = DataEncoder.from_typed_data(typed_data).hash_message()
    signer_instance = StarkCurveSigner(order_params['account_address'], private_key, chain_id) # исправлено, используем экземпляр
    signature = signer_instance.sign(message_hash) # исправлено, используем экземпляр

    return [str(signature.r), str(signature.s)]