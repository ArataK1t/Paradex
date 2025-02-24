from starknet_py.common import int_from_bytes
from starknet_py.utils.typed_data import TypedData
from starknet_py.constants import EC_ORDER
from starknet_crypto_py import sign as rs_sign

def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    import random
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
                {"name": "name", "type": "string"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "string"},
            ],
            "Request": [
                {"name": "method", "type": "string"},
                {"name": "path", "type": "string"},
                {"name": "body", "type": "string"},
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

def generate_starknet_order_signature(order_params: dict, private_key_hex: str, paradex_config: dict) -> list[str]:
    chain_id = int_from_bytes(paradex_config["starknet_chain_id"].encode())
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
                {"name": "price", "type": "felt"},
            ],
        },
        "message": {
            "timestamp": int(order_params['signature_timestamp']),
            "market": order_params['market'],
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
