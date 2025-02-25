import time
from typing import Dict
from starknet_py.utils.typed_data import TypedData
from starknet_py.common import int_from_bytes


def build_auth_message(chainId: int, now: int, expiry: int) -> TypedData:
    message = {
        "message": {
            "method": "POST",
            "path": "/v1/auth",
            "body": "",
            "timestamp": now,
            "expiration": expiry,
        },
        "domain": {"name": "Paradex", "chainId": hex(chainId), "version": "1"},
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
    return TypedData.from_dict(message) # Исправлено: Возвращаем TypedData.from_dict

def build_order_message(chain_id: int, order_params: Dict) -> TypedData:
    """
    Создает TypedData сообщение для подписи ордера.
    """
    order_msg = {
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
        "primaryType": "Order",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "string"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "string"},
            ],
            "Order": [
                {"name": "timestamp", "type": "felt"},
                {"name": "market", "type": "string"},
                {"name": "side", "type": "string"},
                {"name": "orderType", "type": "string"},
                {"name": "size", "type": "felt"},
                {"name": "price", "type": "felt"}, # Цена опциональна, поэтому felt
            ],
        },
        "message": {
            "timestamp": int(order_params['signature_timestamp']),
            "market": order_params['market'],
            "side": "1" if order_params['side'] == "BUY" else "2", # 1 для BUY, 2 для SELL
            "orderType": order_params['type'],
            "size": int(order_params['size']),
            "price": int(order_params.get('price', 0)), # Цена опциональна, 0 по умолчанию
        },
    }
    return TypedData.from_dict(order_msg) # Исправлено: Возвращаем TypedData.from_dict