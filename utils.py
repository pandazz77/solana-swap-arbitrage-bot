import requests
from loguru import logger
from solana.publickey import PublicKey
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts

def get_amm_id(baseMint:str): # baseMint - token address
    pools = requests.get('https://api.raydium.io/v2/sdk/liquidity/mainnet.json').json()
    pools_list = [*pools["official"],*pools["unOfficial"]]
    for pool in pools_list:
        if pool["baseMint"] == baseMint:
            return pool["id"]
    raise Exception(f'{baseMint} baseMint not found!')

def extract_pool_info(pools_list: list, pool_id: str) -> dict:
    pools_list = [*pools_list["official"],*pools_list["unOfficial"]]
    for pool in pools_list:
        if pool['id'] == pool_id:
            return pool
    raise Exception(f'{pool_id} pool not found!')


def fetch_pool_keys(pool_id: str):
    pools = requests.get('https://api.raydium.io/v2/sdk/liquidity/mainnet.json').json()
    amm_info = extract_pool_info(pools, pool_id)
    return {
        'amm_id': PublicKey(pool_id),
        'authority': PublicKey(amm_info['authority']),
        'base_mint': PublicKey(amm_info['baseMint']),
        'base_decimals': amm_info['baseDecimals'],
        'quote_mint': PublicKey(amm_info['quoteMint']),
        'quote_decimals': amm_info['quoteDecimals'],
        'lp_mint': PublicKey(amm_info['lpMint']),
        'open_orders': PublicKey(amm_info['openOrders']),
        'target_orders': PublicKey(amm_info['targetOrders']),
        'base_vault': PublicKey(amm_info['baseVault']),
        'quote_vault': PublicKey(amm_info['quoteVault']),
        'market_id': PublicKey(amm_info['marketId']),
        'market_base_vault': PublicKey(amm_info['marketBaseVault']),
        'market_quote_vault': PublicKey(amm_info['marketQuoteVault']),
        'market_authority': PublicKey(amm_info['marketAuthority']),
        'bids': PublicKey(amm_info['marketBids']),
        'asks': PublicKey(amm_info['marketAsks']),
        'event_queue': PublicKey(amm_info['marketEventQueue'])
    }


def get_token_account(endpoint: str, owner: PublicKey, mint: PublicKey):
    account_data = Client(endpoint).get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
    if account_data["result"]["value"] == []: return PublicKey("So11111111111111111111111111111111111111112")
    return PublicKey(account_data['result']['value'][0]['pubkey'])


def sale_info(balance_before: dict, balance_after: dict):
    base_symbol, quote_symbol = balance_before.keys()
    base_before, quote_before = balance_before.values()
    base_after, quote_after = balance_after.values()
    sold_amount = base_before - base_after
    quote_received = quote_after - quote_before
    price = quote_received / sold_amount
    logger.info(
        f'Sold {sold_amount} {base_symbol}, price: {price} {quote_symbol}, {quote_symbol} received: {quote_received}')


def purchase_info(balance_before: dict, balance_after: dict):
    base_symbol, quote_symbol = balance_before.keys()
    base_before, quote_before = balance_before.values()
    base_after, quote_after = balance_after.values()
    bought_amount = base_after - base_before
    quote_spent = quote_before - quote_after
    price = quote_spent / bought_amount
    logger.info(
        f'Bought {bought_amount} {base_symbol}, price: {price} {quote_symbol}, {quote_symbol} spent: {quote_spent}')
