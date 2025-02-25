from enum import IntEnum
from typing import Tuple

from starknet_py.common import int_from_bytes
from starknet_py.net.client import Client
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import TransactionExecutionStatus, TransactionFinalityStatus
from starknet_py.net.models import Address, Hash
from starknet_py.proxy.proxy_check import ArgentProxyCheck, OpenZeppelinProxyCheck, ProxyCheck
from starknet_py.proxy.contract_abi_resolver import ProxyConfig
from starknet_py.transaction_errors import TransactionRevertedError, TransactionNotReceivedError
from starknet_py.net.client_models import Call
from starknet_py.hash.selector import get_selector_from_name
import asyncio
import re
from typing import Callable, Optional, Dict
import random
from web3.auto import Web3, w3
from web3.middleware import construct_sign_and_send_raw_middleware
from eth_account.signers.local import LocalAccount


def get_chain_id(chain_id: str):
    class CustomStarknetChainId(IntEnum):
        PRIVATE_TESTNET = int_from_bytes(chain_id.encode("UTF-8"))
    return CustomStarknetChainId.PRIVATE_TESTNET


def get_account(account_address: str, account_key: str, paradex_config: dict):
    from helpers.account import Account  # Импортируем Account локально, чтобы избежать циклического импорта
    from starknet_py.net.full_node_client import FullNodeClient # Импортируем FullNodeClient локально
    from starknet_py.net.signer.stark_curve_signer import KeyPair # Импортируем KeyPair локально

    client = FullNodeClient(node_url=paradex_config["starknet_fullnode_rpc_url"])
    key_pair = KeyPair.from_private_key(key=hex_to_int(account_key))
    chain = get_chain_id(paradex_config["starknet_chain_id"])
    account = Account(
        client=client,
        address=account_address,
        key_pair=key_pair,
        chain=chain,
    )
    return account


def get_random_max_fee(start=1e18, end=1e19) -> int:
    return random.randint(start, end)


def get_proxy_config():
    return ProxyConfig(
        max_steps=5,
        proxy_checks=[StarkwareETHProxyCheck(), ArgentProxyCheck(), OpenZeppelinProxyCheck()],
    )


class StarkwareETHProxyCheck(ProxyCheck):
    async def implementation_address(self, address: Address, client: Client) -> Optional[int]:
        return await self.get_implementation(
            address=address,
            client=client,
            get_class_func=client.get_class_hash_at,
            regex_err_msg=r"(is not deployed)",
        )

    async def implementation_hash(self, address: Address, client: Client) -> Optional[int]:
        return await self.get_implementation(
            address=address,
            client=client,
            get_class_func=client.get_class_by_hash,
            regex_err_msg=r"(is not declared)",
        )

    @staticmethod
    async def get_implementation(
        address: Address, client: Client, get_class_func: Callable, regex_err_msg: str
    ) -> Optional[int]:
        call = StarkwareETHProxyCheck._get_implementation_call(address=address)
        err_msg = r"(Entry point 0x[0-9a-f]+ not found in contract)|" + regex_err_msg
        try:
            (implementation,) = await client.call_contract(call=call)
            await get_class_func(implementation)
        except ClientError as err:
            if (re.search(err_msg, err.message, re.IGNORECASE) or err.code == rpc_contract_error_code):
                return None
            raise err
        return implementation

    @staticmethod
    def _get_implementation_call(address: Address) -> Call:
        return Call(
            to_addr=address,
            selector=get_selector_from_name("implementation"),
            calldata=[],
        )
        
# Placeholder for rpc_contract_error_code, you might need to define or import it if used elsewhere
rpc_contract_error_code = -32603 # Example, adjust if needed based on starknet_py.constants


# Forked from https://github.com/software-mansion/starknet.py/blob/development/starknet_py/net/client.py#L134
# Method tweaked to wait for ACCEPTED_ON_L1 status
async def wait_for_tx(
    client: Client, tx_hash: Hash, check_interval=5
) -> Tuple[int, TransactionFinalityStatus]:
    """
    Awaits for transaction to get accepted or at least pending by polling its status

    :param client: Instance of Client
    :param tx_hash: Transaction's hash
    :param check_interval: Defines interval between checks
    :return: Tuple containing block number and transaction status
    """
    if check_interval <= 0:
        raise ValueError("Argument check_interval has to be greater than 0.")

    try:
        while True:
            result = await client.get_transaction_receipt(tx_hash=tx_hash)

            if result.execution_status == TransactionExecutionStatus.REVERTED:
                raise TransactionRevertedError(
                    message=result.revert_reason,
                )

            if result.finality_status == TransactionFinalityStatus.ACCEPTED_ON_L1:
                assert result.block_number is not None
                return result.block_number, result.finality_status

            await asyncio.sleep(check_interval)
    except asyncio.CancelledError as exc:
        raise TransactionNotReceivedError from exc


def get_l1_eth_account(eth_private_key_hex: str) -> Tuple[Web3, LocalAccount]:
    w3.eth.account.enable_unaudited_hdwallet_features()
    account: LocalAccount = w3.eth.account.from_key(eth_private_key_hex)
    w3.eth.default_account = account.address
    w3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    return w3, account


def hex_to_int(val: str):
    return int(val, 16)