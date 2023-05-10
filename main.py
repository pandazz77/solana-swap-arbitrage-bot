import asyncio
import json
import traceback
from typing import Any

from loguru import logger

from CEX import CEX
from raydium_amm import Liquidity
from utils import purchase_info, sale_info, get_amm_id

logger.add('bot.csv', format="{time:YYYY-MM-DD HH:mm:ss},{level},{message}")

amm: Liquidity
cex: CEX
config: Any

"""
{
  "ammPoolId": "",
  "symbol": "SOL/USDT",
  "cexAPIKey": "",
  "cexSecretKey": "",
  "walletSecretKey": "",
  "tradeUsdAmount": 20,
  "priceDiffPercent": 0.5,
  "pause": 5,
  "solanaEndpoint": "https://solana-api.projectserum.com"
}
"""


def load_conf():
    logger.info('Loading config...')
    global config
    with open('config.json') as f:
        config = json.load(f)


async def monitor_prices():
    while True:
        try:
            amm.open()
            cex.open()

            amm_balance_after = await amm.get_balance()
            logger.info(f'AMM balance: {amm_balance_after}')
            cex_balance_after = await cex.get_balance()
            logger.info(f'CEX balance: {cex_balance_after}')
            amm_buy_price, amm_sell_price = await amm.get_prices()
            cex_ask_price, cex_bid_price = await cex.get_prices()
            logger.info(f'AMM buy price: {amm_buy_price}, CEX sell price: {cex_bid_price}')
            logger.info(f'CEX buy price: {cex_ask_price}, AMM sell price {amm_sell_price}')

            if cex_bid_price > amm_buy_price:
                await check_opportunity(amm_buy_price, cex_bid_price, True)
            if amm_sell_price > cex_ask_price:
                await check_opportunity(amm_sell_price, cex_ask_price, False)

            await asyncio.sleep(config['pause'])
            logger.info("")
        except IndexError:
            pass
        except Exception as e:
            logger.error(f'Error in monitor_prices(): {e}')
            traceback.print_exc()

        # Closing connection
        await amm.close()
        await cex.close()


async def check_opportunity(dex_price, cex_price, buy_on_dex):
    price_diff = abs(dex_price - cex_price)
    logger.info(f'AMM price: {dex_price}, cex price: {cex_price}')
    diff_percent = price_diff / dex_price * 100 if buy_on_dex else price_diff / cex_price * 100
    logger.info(f'Diff percent {diff_percent}')
    if diff_percent >= config['priceDiffPercent']:
        # First make sure that the deal will be profitable
        amm_balance = await amm.get_balance()
        cex_balance = await cex.get_balance()
        if buy_on_dex:
            estimate_buy_amount = round(config['tradeUsdAmount'] / dex_price, 5)
            estimate_sell_usd, cex_price, execution_price = await cex.calc_sell_usd_amount(estimate_buy_amount)
            logger.info(f'Estimated sell price: {cex_price}')
        else:
            estimate_buy_amount, cex_price, execution_price = await cex.calc_buy_amount(config['tradeUsdAmount'])
            estimate_sell_usd = estimate_buy_amount * dex_price
            logger.info(f'Estimated buy price: {cex_price}')

        logger.info(f'Estimated buy amount: {estimate_buy_amount}')
        logger.info(f'Estimated sell USD amount: {estimate_sell_usd}')

        # Profit percent formula (1 - (input_amount / output_amount)) * 100
        profit_percent = (1 - (config['tradeUsdAmount'] / estimate_sell_usd)) * 100
        logger.info(f'Profit percent: {profit_percent}%')
        if profit_percent < config['priceDiffPercent']:
            logger.info(f'Not profitable, skipping\n')
            return

        await perform_arbitrage(buy_on_dex, cex_price, execution_price, estimate_buy_amount)

        # Wait for balance update and display balance changes after BUY and SELL
        amm_balance_after = await amm.wait_for_updated_balance(balance_before=amm_balance)
        logger.info(f'AMM balance: {amm_balance_after}')
        cex_balance_after = await cex.get_balance()
        logger.info(f'CEX balance: {cex_balance_after}')
        if buy_on_dex:
            logger.info('On AMM:')
            purchase_info(amm_balance, amm_balance_after)
            logger.info('On CEX:')
            sale_info(cex_balance, cex_balance_after)
        else:
            logger.info('On CEX:')
            purchase_info(cex_balance, cex_balance_after)
            logger.info('On AMM:')
            sale_info(amm_balance, amm_balance_after)


async def perform_arbitrage(buy_on_dex: bool, cex_price, execution_price, amount):
    logger.info(f'Buy on AMM: {buy_on_dex}')
    if buy_on_dex:
        res = await amm.buy(config['tradeUsdAmount'])
        await cex.sell(amount, cex_price, execution_price)
    else:
        await cex.buy(amount, cex_price, execution_price)
        res = await amm.sell(amount)
    logger.info(f'Tx hash: {res["result"]}, waiting confirmation...')


async def main():
    global amm, cex
    load_conf()
    amm = Liquidity(
        config['solanaEndpoint'],
        get_amm_id(config["baseMint"]),
        config['walletSecretKey'],
        config['symbol']
    )
    cex = CEX(config['symbol'], config['cexAPIKey'], config['cexSecretKey'])
    await monitor_prices()
    # estimate_sell_usd, cex_price, execution_price = await cex.calc_sell_usd_amount(1)
    # await cex.buy(1, cex_price, execution_price)
    # print(await amm.sell(2))


if __name__ == '__main__':
    asyncio.run(main())
