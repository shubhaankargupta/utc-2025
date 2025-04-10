from typing import Optional

from utcxchangelib import xchange_client
import numpy as np
from scipy.stats import lognorm
import asyncio
import argparse

#IP address: 18.222.177.21
#Password: Hrb8t5)V&q

class MyXchangeClient(xchange_client.XChangeClient):

    def __init__(self, host: str, username: str, password: str):
        super().__init__(host, username, password)
        self.fair_prices = {symbol : 0 for symbol in ['AKAV', 'AKIM', 'APT', 'DLR', 'MKJ']}
        self.updates = {symbol : 0 for symbol in ['AKAV', 'AKIM', 'APT', 'DLR', 'MKJ']}
        self.market_fair_prices = {symbol : 0 for symbol in ['AKAV', 'AKIM', 'APT', 'DLR', 'MKJ']}
    async def bot_handle_cancel_response(self, order_id: str, success: bool, error: Optional[str]) -> None:
        order = self.open_orders[order_id]
        print(f"{'Market' if order[2] else 'Limit'} Order ID {order_id} cancelled, {order[1]} unfilled")

    async def bot_handle_order_fill(self, order_id: str, qty: int, price: int):
        print("order fill", self.positions)

    async def bot_handle_order_rejected(self, order_id: str, reason: str) -> None:
        print("order rejected because of ", reason)


    async def bot_handle_trade_msg(self, symbol: str, price: int, qty: int):
        pass

    async def bot_handle_book_update(self, symbol: str) -> None:
        pass

    async def bot_handle_swap_response(self, swap: str, qty: int, success: bool):
        pass

    async def bot_handle_news(self, news_release: dict):

        # Parsing the message based on what type was received
        # APT, DLR, MKJ have different types of ways to handle the messages. 
        # Use to figure out how to modify fair value of these securities
        timestamp = news_release["timestamp"] # This is in exchange ticks not ISO or Epoch
        news_type = news_release['kind']
        news_data = news_release["new_data"]

        if news_type == "structured":
            subtype = news_data["structured_subtype"]
            symb = news_data["asset"]
            if subtype == "earnings":
                self.updates['APT'] += 1
                earnings = news_data["value"]
                self.fair_prices['APT'] = 10 * earnings #may have to change this value during the actual competition
                #trade around this value
            else:
                self.updates['DLR'] += 1
                new_signatures = news_data["new_signatures"]
                cumulative = news_data["cumulative"]
                #S_i = lognormal(log a + log S_(i-1), sigma^2)
                #S_0 = 5000, alpha = 1.0630449594499
                #sigma = 0.006
                alpha = 1.0630449594499
                sigma = 0.006
                log_alpha = np.log(alpha)
                rounds_remaining = 50 - self.updates['DLR']
                print("CUMULATIVE, ROUNDS REMAINING ARE", cumulative, rounds_remaining)
                # good_sims = 0
                # #just gonna do a monte carlo here lol
                # for i in range(1000): #1000 sims
                #     init_new_sigs = cumulative
                #     for j in range(rounds_remaining):
                #         mu = np.log(init_new_sigs) + log_alpha
                #         init_new_sigs = np.random.lognormal(mean=mu, sigma=0.006)
                #     good_sims += (init_new_sigs >= 100000)
                mu = np.log(cumulative) + rounds_remaining * np.log(alpha)  
                tau = np.sqrt(rounds_remaining * sigma**2)
                prob = 1 - lognorm.cdf(100000, s = tau, scale=np.exp(mu))
                self.fair_prices['DLR'] = prob * 10000
                # EV = 100 * p(will reach 100,000 sigs), so trade around this fair price

        else:
            increased = 0
            print(f"previous fair price is {self.fair_prices['MKJ']}")
            prev_fair = self.fair_prices['MKJ']
            highest_bid, lowest_ask = 0, 0
            for security, book in self.order_books.items():
                if security == 'MKJ':
                    highest_bid = max(((k,v) for k,v in book.bids.items() if v != 0))[0]
                    lowest_ask = min(((k,v) for k,v in book.asks.items() if v != 0))[0]
                    
                    if highest_bid and lowest_ask and highest_bid < lowest_ask + 1:
                        fair_price = (highest_bid + lowest_ask)//2
                        if fair_price > prev_fair:
                            print(f"difference is {fair_price}, {self.fair_prices['MKJ']}")
                            self.fair_prices['MKJ'] = fair_price
                            increased = 1


            # for a slight competitive edge, there are SOME messages that might guarantee positive PNL.
                    
            print(news_release)
            f = open("unstructured3.txt", "a")
            news = news_release['new_data']['content']
            f.write(f'{news}: {increased} with previous fair price at {prev_fair}, new at {fair_price}\n')

            # Trying to correlate news with positive/negative gain, data on a different file.
            # Think this has to do with click trading, actually. 

    #super simple strategy implementation
    #for every trade that's made, update fair price to most recently transacted value
    #then offer bid/ask around that value
    async def trade(self): 
        self.fair_prices['DLR'] = self.market_fair_prices['DLR'] = 5000
        self.fair_prices['APT'] = self.market_fair_prices['APT'] = 1000
        self.fair_prices['MKJ'] = self.market_fair_prices['MKJ'] = 1000
        self.fair_prices['AKAV'] = self.market_fair_prices['AKAV'] = 7000
        self.fair_prices['AKIM'] = self.market_fair_prices['AKIM'] = 8000 # for now

        #update these later
        
        self.updates['DLR'] = 0
        while True:

            await asyncio.sleep(1)
            for symbol in ['APT', 'DLR', 'MKJ', 'AKAV', 'AKIM']:
                book = self.order_books[symbol]
                sorted_bids = sorted((k,v) for k,v in book.bids.items() if v != 0)
                sorted_asks = sorted((k,v) for k,v in book.asks.items() if v != 0)
                print(f"Bids for {symbol}:\n{sorted_bids}")
                print(f"Asks for {symbol}:\n{sorted_asks}")
                if sorted_bids and sorted_asks:
                    bids_max = sorted_bids[-1][0]
                    ask_min = sorted_asks[0][0]
                    if bids_max < ask_min + 1:
                        self.market_fair_prices[symbol] = (bids_max + ask_min)//2
                    else:
                        self.market_fair_prices[symbol] = self.fair_prices[symbol]
                if symbol in ['MKJ', 'AKAV', 'AKIM']:
                    self.fair_prices[symbol] = self.market_fair_prices[symbol]
                # if there are no spreads, might also be worth it to just _not_ trade the stock at that moment
                #         
                print(f"Market fair price for {symbol} is {self.market_fair_prices[symbol]}\n")

            for asset in ['APT', 'DLR']:
                fair_price = self.fair_prices[asset]
                market_buy_id = await self.place_order(asset, 1, xchange_client.Side.BUY, int(fair_price-2))
                market_sell_id = await self.place_order(asset, 1, xchange_client.Side.SELL, int(fair_price + 2))
                print(f"ORDERS PLACED FOR {asset}, buy at {fair_price-2}, sell at {fair_price+2}")
            
            mkj_price = self.market_fair_prices['MKJ']
            mkj_buy_id = await self.place_order('MKJ', 1, xchange_client.Side.BUY, int(mkj_price-2))
            market_sell_id = await self.place_order('MKJ', 1, xchange_client.Side.SELL, int(mkj_price + 2))


            # etf_mm = True
            # for asset in ['APT', 'DLR', 'MKJ', 'AKAV']:
            #     if asset not in self.spreads:
            #         etf_mm = False
            # #Note: do not put any sleep() statements here bc orderbooks might update too fast
            # #We want most updated prices

            # #our fair buy price = best bid + 1
            # #our fair sell price = best ask - 1
            # #if we have an etf at best bid + 1, it's optimal to buy if best bid + 1 (etf) + 5 < sum (fair buy prices)
            # #if we have an etf at best_ask - 1, it's optimal to sell if sum (fair sell prices) + 5 < best_sell -1
            akav_fair_price = 0
            for asset in ['APT', 'DLR', 'MKJ']:
                akav_fair_price += self.fair_prices[asset]
            print("\nETF market making\n")
            akav_market_price = self.fair_prices['AKAV']
            if akav_market_price + 5 < akav_fair_price:
                #buy etf, convert it back to individual stocks, buy them on exchange
                #math time: if we buy etf for price p -> convert to x, y, z (our fair prices for buying)
                spread = akav_fair_price - akav_market_price - 5
                self.place_order('AKAV', 1, xchange_client.Side.BUY, akav_market_price + spread - 2)
                self.place_order('AKIM', 1, xchange_client.SIDE.SELL, self.market_fair_prices['AKIM']) 
                # if self.positions['AKAV'] > 0:
                    
                #     for asset in ['APT', 'DLR']:
                #         fair_price = self.fair_prices[asset]
                #         market_buy_id = await self.place_order(asset, 1, xchange_client.Side.BUY, int(fair_price-2))
                #         market_sell_id = await self.place_order(asset, 1, xchange_client.Side.SELL, int(fair_price + 2))
                #         print(f"ORDERS PLACED FOR {asset}, buy at {fair_price-2}, sell at {fair_price+2}")
        
                #     mkj_buy_id = await self.place_order('MKJ', 1, xchange_client.Side.BUY, int(fair_price-2))
                #     market_sell_id = await self.place_order('MKJ', 1, xchange_client.Side.SELL, int(fair_price + 2))
                print(f"ETF AKAV PRICED AT {akav_market_price}, SUM OF ASSETS IS {akav_fair_price}, UNBUNDLE ETF -> ASSETS\n")

            elif akav_market_price > akav_fair_price + 5:
                self.place_swap_order('toAKAV', 1)
                self.place_order('AKIM', 1, xchange_client.SIDE.BUY, self.market_fair_prices['AKIM']-1)
                print(f"ETF AKAV PRICED AT {akav_market_price}, SUM OF ASSETS IS {akav_fair_price}, BUNDLE ASSETS INTO ETFs \n")
            #This gives fairly good PNL against bots, but this is because bots are dumb
            #Next: figuring out how to price assets in a better manner
            #Also, figure out how to price ETFs. Might want to learn how to hedge AKIM w/ AKAV
            print("my positions:", self.positions)
        # await self.cancel_order(list(self.open_orders.keys())[0])
        # await self.place_swap_order('toAKAV', 1)
        # await asyncio.sleep(5)
        # await self.place_swap_order('fromAKAV', 1)
        # await asyncio.sleep(5)
        # await self.place_order("APT",1000, xchange_client.Side.SELL, 7)
        # market_order_id = await self.place_order("APT",10, xchange_client.Side.SELL)
        # print("MARKET ORDER ID:", market_order_id)

    async def view_books(self) -> None:
        for security, book in self.order_books.items():
            sorted_bids = sorted((k,v) for k,v in book.bids.items() if v != 0)
            sorted_asks = sorted((k,v) for k,v in book.asks.items() if v != 0)
            print(f"Bids for {security}:\n{sorted_bids}")
            print(f"Asks for {security}:\n{sorted_asks}")
    
    async def start(self, user_interface):
        asyncio.create_task(self.trade())

        # This is where Phoenixhood will be launched if desired. There is no need to change these
        # lines, you can either remove the if or delete the whole thing depending on your purposes.
        if user_interface:
            self.launch_user_interface()
            asyncio.create_task(self.handle_queued_messages())

        await self.connect()


user_interface = False

async def main(user_interface : bool):
    # SERVER = '127.0.0.1:8000'   # run locally
    SERVER = '3.138.154.148:3333' # run sandbox
    my_client = MyXchangeClient(SERVER,"chicago4","Hrb8t5)V&q")
    await my_client.start(user_interface)
    return

if __name__ == "__main__":

    # This parsing is unnecessary if you know whether you are using Phoenixhood.
    # It is included here so you can see how one might start the API.

    parser = argparse.ArgumentParser(
        description="Script that connects client to exchange, runs algorithmic trading logic, and optionally deploys Phoenixhood"
    )

    parser.add_argument("--phoenixhood", required=False, default=False, type=bool, help="Starts phoenixhood API if true")
    args = parser.parse_args()

    user_interface = args.phoenixhood

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(main(user_interface))


