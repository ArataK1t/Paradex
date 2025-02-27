from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_py.constants import EC_ORDER
from starknet_crypto_py import sign as rs_sign
import json
import random

def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    k = random.randint(1, EC_ORDER - 1)
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k)

def generate_starknet_auth_signature(account_address: str, timestamp: int, expiration: int, private_key_hex: str, paradex_config: dict) -> list[str]:
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
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
    typed_data = TypedData.from_dict(auth_msg)
    account_int = int(account_address, 16)
    msg_hash = typed_data.message_hash(account_int)
    
    priv_key = int(private_key_hex, 16)
    r, s = message_signature(msg_hash, priv_key)
    return [str(r), str(s)]

def flatten_signature(sig: list[str]) -> str:
    return f'["{sig[0]}","{sig[1]}"]'

def generate_starknet_order_signature(order_params: dict, private_key_hex: str, paradex_config: dict, account_address: str) -> str:
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
    
    # Формируем message для подписи.
    # Если order type является MARKET (или аналогичным), поле price исключается.
    order_message = {
        "timestamp": str(order_params['signature_timestamp']),
        "market": order_params['market'],
        "side": order_params['side'],
        "orderType": order_params['type'],
        "size": str(int(float(order_params['size'])))
    }
    if order_params['type'] not in ("MARKET", "STOP_MARKET", "STOP_LOSS_MARKET", "TAKE_PROFIT_MARKET"):
        order_message["price"] = str(int(float(order_params.get('price', 0))))
    
    # Определяем поля типа Order – аналогично исключаем price для MARKET-ордеров.
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
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
        "primaryType": "Order",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "Order": order_fields
        },
        "message": order_message,
    }
    
    print(f"TypedData для ордера (JSON):\n{json.dumps(order_msg, indent=2)}")
    
    typed_data = TypedData.from_dict(order_msg)
    # Используем 0 вместо account_address для вычисления хеша (так как поле не входит в сообщение)
    msg_hash = typed_data.message_hash(0)
    print(f"Message Hash для ордера: {msg_hash}")
    
    r, s = message_signature(msg_hash, int(private_key_hex, 16))
    sig = [str(r), str(s)]
    signature_str = flatten_signature(sig)
    return signature_str
