import ccxt.async_support as ccxt
from loguru import logger


class CEX:

    def __init__(self, symbol: str, api_key: str, secret_key: str):
        self.symbol = symbol
        self.base_symbol, self.quote_symbol = self.symbol.split('/')
        self.api_key = api_key
        self.secret_key = secret_key
        self.cex = ccxt.huobi({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'timeout': 60000
        })

    async def get_balance(self):
        balance = await self.cex.fetch_free_balance()
        return {self.base_symbol: balance[self.base_symbol], self.quote_symbol: balance[self.quote_symbol]}

    def open(self):
        self.cex.open()

    async def close(self):
        await self.cex.close()

    async def get_prices(self):
        order_book = await self.cex.fetch_order_book(self.symbol, limit=5)
        return order_book['asks'][0][0], order_book['bids'][0][0]

    async def get_order_book(self):
        return await self.cex.fetch_order_book(self.symbol, limit=20)

    async def calc_sell_usd_amount(self, amount):
        bids = (await self.get_order_book())['bids']
        amount_to_sell = amount
        usd_amount = 0
        for i in range(len(bids)):
            if amount_to_sell == 0:
                return round(usd_amount, 5), bids[i][0], bids[i + 4][0]
            if bids[i][1] > amount_to_sell:
                usd_amount += bids[i][0] * amount_to_sell  # price * amount_to_sell
                amount_to_sell = 0
            else:
                usd_amount += bids[i][0] * bids[i][1]
                amount_to_sell -= bids[i][1]

    async def calc_buy_amount(self, usd_amount):
        """
        Calculates what amount of token can be bought for given usd_amount
        :returns: tuple(amount to buy, starting buy price, ending buy price)
        """
        asks = (await self.get_order_book())['asks']
        amount_to_buy = 0
        for i in range(len(asks)):
            if usd_amount == 0:
                return round(amount_to_buy, 5), asks[i][0], asks[i + 4][0]
            if asks[i][1] * asks[i][0] > usd_amount:  # quantity * price > buy_usd_amount
                amount_to_buy += usd_amount / asks[i][0]
                usd_amount = 0
            else:
                amount_to_buy += asks[i][1]
                usd_amount -= asks[i][1] * asks[i][0]

    async def sell(self, amount, price, execution_price):
        res = await self.cex.create_limit_sell_order(self.symbol, amount, execution_price)
        logger.info(f'Sold {amount} {self.base_symbol}, price: {price} {self.quote_symbol} on CEX: {res}')

    async def buy(self, amount, price, execution_price):
        res = await self.cex.create_limit_buy_order(self.symbol, amount, execution_price)
        logger.info(f'Bought {amount} {self.base_symbol} for {price} {self.quote_symbol} on CEX: {res}')
