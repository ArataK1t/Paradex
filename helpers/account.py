from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union
from starknet_py.constants import EC_ORDER
from starknet_crypto_py import sign as rs_sign

from starknet_py.common import (
    CairoVersion,
    InvokeFunctionArgs,
    Signature,
    TransactionHash,
)
from starknet_py.constants import DEFAULT_DEPLOYER_ADDRESS
from starknet_py.hash.address import compute_contract_address
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.account.account import Account
from starknet_py.net.client import Client
from starknet_py.net.client_models import Call, TransactionType, Hash
from starknet_py.net.models import AddressRepresentation
from starknet_py.net.models.transaction import (
    AccountDeployment,
    Declare,
    DeployAccount,
    Invoke,
    PreparedDeclareTransaction,
    PreparedDeployAccountTransaction,
    PreparedTransaction,
)
from starknet_py.net.signer import BaseSigner
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.proxy.contract_abi_resolver import ProxyConfig
from starknet_py.proxy.proxy_check import ProxyCheck
from starknet_py.utils.typed_data import TypedData


@dataclass
class AccountVersion:
    version: int

    @property
    def invoke_transaction_version(self) -> int:
        return self.version

    @property
    def deploy_account_transaction_version(self) -> int:
        return self.version

    @property
    def declare_transaction_version(self) -> int:
        return self.version


ACCOUNT_VERSIONS = {
    0: AccountVersion(version=1),
    1: AccountVersion(version=1),
    2: AccountVersion(version=2),
}


class StarknetAccount(Account):
    def __init__(
        self,
        client: Client,
        address: AddressRepresentation,
        key_pair: KeyPair,
        chain: Union[str, int],
        supported_tx_versions: Optional[Sequence[int]] = None,
        cairo_version: CairoVersion = "0",
        layout: Optional[str] = None,
    ):
        super().__init__(
            client=client,
            address=address,
            key_pair=key_pair,
            chain=chain,
            supported_tx_versions=supported_tx_versions,
            cairo_version=cairo_version,
            layout=layout,
        )
        self._supported_account_versions = supported_tx_versions or [0, 1, 2]

    def _get_account_version(self, version: int) -> AccountVersion:
        if version not in self._supported_account_versions:
            raise ValueError(
                f"Provided transaction version: {version} is not supported by this Account instance. "
                f"Supported versions are: {self._supported_account_versions}."
            )
        return ACCOUNT_VERSIONS[version]

    async def sign_message(self, typed_data: TypedData) -> Signature:
        return self.signer.sign_message(typed_data=typed_data, key_pair=self.key_pair)

    async def execute(
        self,
        calls: Union[Call, List[Call]],
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
        version: int = 1,
    ) -> Invoke:
        version = self._get_account_version(version).invoke_transaction_version
        return await super().execute(
            calls=calls, max_fee=max_fee, auto_estimate=auto_estimate, version=version
        )

    async def execute_v1(
        self,
        calls: Union[Call, List[Call]],
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
    ) -> Invoke:
        return await self.execute(calls=calls, max_fee=max_fee, auto_estimate=auto_estimate, version=1)

    async def execute_v2(
        self,
        calls: Union[Call, List[Call]],
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
    ) -> Invoke:
        return await self.execute(calls=calls, max_fee=max_fee, auto_estimate=auto_estimate, version=2)

    async def declare(
        self,
        prepared_tx: PreparedDeclareTransaction,
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
        version: int = 1,
    ) -> Declare:
        version = self._get_account_version(version).declare_transaction_version
        return await super().declare(
            prepared_tx=prepared_tx, max_fee=max_fee, auto_estimate=auto_estimate, version=version
        )

    async def declare_v1(
        self,
        prepared_tx: PreparedDeclareTransaction,
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
    ) -> Declare:
        return await self.declare(
            prepared_tx=prepared_tx, max_fee=max_fee, auto_estimate=auto_estimate, version=1
        )

    async def declare_v2(
        self,
        prepared_tx: PreparedDeclareTransaction,
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
    ) -> Declare:
        return await self.declare(
            prepared_tx=prepared_tx, max_fee=max_fee, auto_estimate=auto_estimate, version=2
        )

    async def deploy_account(
        self,
        prepared_tx: PreparedDeployAccountTransaction,
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
        version: int = 1,
    ) -> DeployAccount:
        version = self._get_account_version(version).deploy_account_transaction_version
        return await super().deploy_account(
            prepared_tx=prepared_tx, max_fee=max_fee, auto_estimate=auto_estimate, version=version
        )

    async def deploy_account_v1(
        self,
        prepared_tx: PreparedDeployAccountTransaction,
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
    ) -> DeployAccount:
        return await self.deploy_account(
            prepared_tx=prepared_tx, max_fee=max_fee, auto_estimate=auto_estimate, version=1
        )

    async def deploy_account_v2(
        self,
        prepared_tx: PreparedDeployAccountTransaction,
        *,
        max_fee: Optional[int] = None,
        auto_estimate: bool = False,
    ) -> DeployAccount:
        return await self.deploy_account(
            prepared_tx=prepared_tx, max_fee=max_fee, auto_estimate=auto_estimate, version=2
        )


class Account(StarknetAccount):
    """
    Account implementation using Custom Signer and TypedData for message signing.
    """

    def sign_message(self, typed_data: TypedData) -> Signature:
        """
        Signs TypedData message using custom signing logic.
        """
        return generate_custom_signature(typed_data, self.key_pair.private_key, self.address)


def generate_custom_signature(typed_data: TypedData, private_key: int, account_address: int) -> Signature:
    """
    Generates custom signature for TypedData message.
    """
    message_hash = compute_message_hash(typed_data, account_address)
    r, s = message_signature(msg_hash, private_key)
    return [r, s]


def compute_message_hash(typed_data: TypedData, account_address: int) -> int:
    """
    Computes message hash for TypedData message, including account address in domain.
    """
    domain_params = typed_data.domain.copy()
    domain_params["verifyingContract"] = hex(account_address)  # Добавляем address аккаунта в domain
    message = TypedData(
        types=typed_data.types,
        primary_type=typed_data.primary_type,
        domain=domain_params,
        message=typed_data.message,
    )
    return message.message_hash()


def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    """
    Signs message hash using starknet_crypto_py.
    """
    import random
    k = random.randint(1, EC_ORDER - 1)
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k)