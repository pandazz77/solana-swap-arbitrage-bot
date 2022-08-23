import asyncio
import re
from ast import literal_eval

import base58
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.transaction import TransactionInstruction, AccountMeta, Transaction

from layouts import SWAP_LAYOUT, POOL_INFO_LAYOUT
from utils import fetch_pool_keys, get_token_account

SERUM_VERSION = 3
AMM_PROGRAM_VERSION = 4

AMM_PROGRAM_ID = PublicKey('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8')
TOKEN_PROGRAM_ID = PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
SERUM_PROGRAM_ID = PublicKey('9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin')

LIQUIDITY_FEES_NUMERATOR = 25
LIQUIDITY_FEES_DENOMINATOR = 10000


def compute_sell_price(pool_info):
    reserve_in = pool_info['pool_coin_amount']
    reserve_out = pool_info['pool_pc_amount']

    amount_in = 1 * 10 ** pool_info['coin_decimals']
    fee = amount_in * LIQUIDITY_FEES_NUMERATOR / LIQUIDITY_FEES_DENOMINATOR
    amount_in_with_fee = amount_in - fee
    denominator = reserve_in + amount_in_with_fee
    amount_out = reserve_out * amount_in_with_fee / denominator
    return amount_out / 10 ** pool_info['pc_decimals']


def compute_buy_price(pool_info):
    reserve_in = pool_info['pool_pc_amount']
    reserve_out = pool_info['pool_coin_amount']

    amount_out = 1 * 10 ** pool_info['coin_decimals']

    denominator = reserve_out - amount_out
    amount_in_without_fee = reserve_in * amount_out / denominator
    amount_in = amount_in_without_fee * LIQUIDITY_FEES_DENOMINATOR / LIQUIDITY_FEES_DENOMINATOR - LIQUIDITY_FEES_NUMERATOR
    return amount_in / 10 ** pool_info['pc_decimals']


class Liquidity:

    def __init__(self, rpc_endpoint: str, pool_id: str, secret_key: str, symbol: str):
        self.endpoint = rpc_endpoint
        self.conn = AsyncClient(self.endpoint, commitment=Commitment("confirmed"))
        self.pool_id = pool_id
        self.pool_keys = fetch_pool_keys(self.pool_id)
        self.owner = Keypair.from_secret_key(base58.b58decode(secret_key))
        self.base_token_account = get_token_account(self.endpoint, self.owner.public_key, self.pool_keys['base_mint'])
        self.quote_token_account = get_token_account(self.endpoint, self.owner.public_key, self.pool_keys['quote_mint'])
        self.base_symbol, self.quote_symbol = symbol.split('/')

    def open(self):
        self.conn = AsyncClient(self.endpoint, commitment=Commitment("confirmed"))

    async def close(self):
        await self.conn.close()

    @staticmethod
    def make_simulate_pool_info_instruction(accounts):
        keys = [
            AccountMeta(pubkey=accounts["amm_id"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["authority"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["open_orders"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["base_vault"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["quote_vault"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["lp_mint"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["market_id"], is_signer=False, is_writable=False),
        ]
        data = POOL_INFO_LAYOUT.build(
            dict(
                instruction=12,
                simulate_type=0
            )
        )
        return TransactionInstruction(keys, AMM_PROGRAM_ID, data)

    def make_swap_instruction(self, amount_in: int, token_account_in: PublicKey, token_account_out: PublicKey,
                              accounts: dict) -> TransactionInstruction:
        keys = [
            AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["amm_id"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["authority"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["open_orders"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["target_orders"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["base_vault"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["quote_vault"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=SERUM_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=accounts["market_id"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["bids"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["asks"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["event_queue"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["market_base_vault"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["market_quote_vault"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=accounts["market_authority"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
            AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
            AccountMeta(pubkey=self.owner.public_key, is_signer=True, is_writable=False)
        ]
        data = SWAP_LAYOUT.build(
            dict(
                instruction=9,
                amount_in=int(amount_in),
                min_amount_out=0
            )
        )
        return TransactionInstruction(keys, AMM_PROGRAM_ID, data)

    async def buy(self, amount):
        swap_tx = Transaction()
        signers = [self.owner]
        token_account_in = self.quote_token_account
        token_account_out = self.base_token_account
        amount_in = amount * 10 ** self.pool_keys['quote_decimals']
        swap_tx.add(
            self.make_swap_instruction(amount_in, token_account_in, token_account_out, self.pool_keys))
        return await self.conn.send_transaction(swap_tx, *signers)

    async def sell(self, amount):
        swap_tx = Transaction()
        signers = [self.owner]
        token_account_in = self.base_token_account
        token_account_out = self.quote_token_account
        amount_in = amount * 10 ** self.pool_keys['base_decimals']
        swap_tx.add(
            self.make_swap_instruction(amount_in, token_account_in, token_account_out, self.pool_keys))
        return await self.conn.send_transaction(swap_tx, *signers)

    async def simulate_get_market_info(self):
        recent_block_hash = (await self.conn.get_recent_blockhash())["result"]["value"]["blockhash"]
        tx = Transaction(recent_blockhash=recent_block_hash, fee_payer=self.owner.public_key)
        tx.add(self.make_simulate_pool_info_instruction(self.pool_keys))
        signers = [self.owner]
        tx.sign(*signers)
        res = (await self.conn.simulate_transaction(tx))['result']['value']['logs'][1]
        pool_info = literal_eval(re.search('({.+})', res).group(0))
        return pool_info

    async def get_prices(self):
        pool_info = await self.simulate_get_market_info()
        return round(compute_buy_price(pool_info), 4), round(compute_sell_price(pool_info), 4)

    async def get_balance(self):
        base_token_balance = (await self.conn.get_token_account_balance(self.base_token_account))['result']['value'][
            'uiAmount']
        quote_token_balance = (await self.conn.get_token_account_balance(self.quote_token_account))['result']['value'][
            'uiAmount']
        return {self.base_symbol: base_token_balance, self.quote_symbol: quote_token_balance}

    async def wait_for_updated_balance(self, balance_before: dict):
        balance_after = await self.get_balance()
        while balance_after == balance_before:
            await asyncio.sleep(1)
            balance_after = await self.get_balance()
        return balance_after
