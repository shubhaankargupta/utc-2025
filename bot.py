from typing import Optional

from utcxchangelib import xchange_client
import numpy as np
import asyncio
import argparse


class MyXchangeClient(xchange_client.XChangeClient):

    def __init__(self, host: str, username: str, password: str):
        super().__init__(host, username, password)

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
        print(news_release)
        timestamp = news_release["timestamp"] # This is in exchange ticks not ISO or Epoch
        news_type = news_release['kind']
        news_data = news_release["new_data"]

        if news_type == "structured":
            subtype = news_data["structured_subtype"]
            symb = news_data["asset"]
            if subtype == "earnings":
                earnings = news_data["value"]
                self.fair_prices['APT'] = 100 * earnings #may have to change this value during the actual competition
                #trade around this value
            else:
                
                new_signatures = news_data["new_signatures"]
                cumulative = news_data["cumulative"]
                #S_i = lognormal(log a + log S_(i-1), sigma^2)
                #S_0 = 5000, alpha = 1.0630449594499
                #sigma = 0.006
                alpha = 1.0630449594499
                sigma = 0.006
                log_alpha = np.log(alpha)
                remaining_sigs = 100000 - cumulative
                ev_per_next_rds = new_signatures * alpha
                rounds_remaining = 50 - self.DLR_updates

                good_sims = 0
                #just gonna do a monte carlo here lol
                for i in range(1000): #1000 sims
                    init_new_sigs = new_signatures
                    for j in range(rounds_remaining):
                        mu = np.log(init_new_sigs) + log_alpha
                        init_new_sigs = np.random.lognormal(mean=mu, sigma=0.006)
                    good_sims += (init_new_sigs >= 100000)

                self.fair_prices['DLR'] = good_sims * 10
                # Do something with this data
                # EV = 100 * p(will reach 100,000 sigs), so trade around this fair price

        else:

            # Not sure what you would do with unstructured data....
            # Think this has to do with click trading, actually. 
            pass

    #super simple strategy implementation
    #for every trade that's made, update fair price to most recently transacted value
    #then offer bid/ask around that value
    async def trade(self):
        await asyncio.sleep(5)  
        self.positions['AKAV'] = 0
        self.positions['AKIM'] = 0
        self.fair_prices['DLR'] = 5000
        while True:

            await asyncio.sleep(1)
            self.spreads = {}
            for symbol in ['APT', 'DLR', 'MKJ', 'AKAV', 'AKIM']:
                bids = self.order_books[symbol].bids
                asks = self.order_books[symbol].asks
                bids_sorted = sorted((k,v) for k,v in bids.items() if v != 0)
                asks_sorted = sorted((k,v) for k,v in asks.items() if v != 0)
                if bids_sorted and asks_sorted:
                    self.spreads[symbol] = (bids_sorted[0], asks_sorted[-1])
                print(f"Bids for {symbol} are {bids_sorted}\n")
                print(f"Asks for {symbol} are {asks_sorted}\n")
            print(f"Spreads are {self.spreads}\n")
            for asset in ['APT', 'DLR']:
                fair_price = self.fair_price[asset]
                market_buy_id = await self.place_order(asset, 4, xchange_client.Side.BUY, fair_price-2)
                market_sell_id = await self.place_order(asset, 4, xchange_client.Side.SELL, fair_price + 2)
                # if asset in self.spreads and (self.spreads)[asset][1][0] - (self.spreads)[asset][0][0] > 2: 
                #     #for latency purposes, might want more efficient ways of getting min/max
                #     #might also want to incorporate fair price evals into this 
                #     #OR we could just let other people do it for us (which is what this strat takes advantage of)

                #     market_buy_id = await self.place_order(asset, 4, xchange_client.Side.BUY, (self.spreads)[asset][0][0]+1)
                #     akav_sum_buy_price += (self.spreads)[asset][0][0] + 1
                #     market_sell_id = await self.place_order(asset, 4, xchange_client.Side.SELL, (self.spreads)[asset][1][0]-1)
                #     akav_sum_sell_price += (self.spreads)[asset][1][0] - 1
                #     print(f"ORDERS PLACED FOR {asset}, buy at {(self.spreads)[asset][0][0]+1}, sell at {(self.spreads)[asset][1][0]-1}")
                    
                    # Strat: frontrun existing bid/asks
                    # Look at the best bid, add 1, look at the best sell, subtract 1
                    # Obviously, don't do this if best sell - best bid < 2, which I'm assuming it will be during the competition
                    # However, as orders fill, our outstanding orders will gradually get processed, which is arb over time
                    # Simplicity = good type shi


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
            # if etf_mm:
            #     #do stuff w/ etfs. for testing purposes
            #     print("\nETF market making\n")
            #     if (self.spreads)['AKAV'][0][0] + 1 + 5 < akav_sum_buy_price:
            #         #buy etf, convert it back to individual stocks, buy them on exchange
            #         #math time: if we buy etf for price p -> convert to x, y, z (our fair prices for buying)
            #         self.place_order('AKAV', 1, xchange_client.Side.BUY, (self.spreads)['AKAV'][0][0] + 1)
            #         if self.positions['AKAV'] > 0:
            #             #assuming its bought, convert 1 share to stocks (idk if this is needed)
            #             self.place_swap_order('fromAKAV', 1)
            #     elif akav_sum_sell_price + 5 < (self.spreads)['AKAV'][1][0] - 1:
            #         self.place_swap_order('toAKAV', 1)
            #         self.place_order('AKAV', 1, xchange_client.Side.SELL, (self.spreads)['AKAV'][1][0] -1)

            #This gives fairly good PNL against bots, but this is because bots are dumb
            #Next: figuring out how to price assets in a better manner
            #Also, figure out how to price ETFs. Might want to learn how to hedge AKIM w/ AKAV
            print("my positions:", self.positions)
            await asyncio.sleep(2)
        # await self.place_order("APT",3, xchange_client.Side.BUY, 5)
        # await self.place_order("APT",3, xchange_client.Side.SELL, 7)
        # await asyncio.sleep(5)
        # await self.cancel_order(list(self.open_orders.keys())[0])
        # await self.place_swap_order('toAKAV', 1)
        # await asyncio.sleep(5)
        # await self.place_swap_order('fromAKAV', 1)
        # await asyncio.sleep(5)
        # await self.place_order("APT",1000, xchange_client.Side.SELL, 7)
        # market_order_id = await self.place_order("APT",10, xchange_client.Side.SELL)
        # print("MARKET ORDER ID:", market_order_id)

    async def view_books(self) -> dict:
        while True:
            await asyncio.sleep(5)
            for security, book in self.order_books.items():
                sorted_bids = sorted((k,v) for k,v in book.bids.items() if v != 0)
                sorted_asks = sorted((k,v) for k,v in book.asks.items() if v != 0)
                print(f"Bids for {security}:\n{sorted_bids}")
                print(f"Asks for {security}:\n{sorted_asks}")
                print(f"Spreads are {self.spreads}")
        
    async def start(self, user_interface):
        asyncio.create_task(self.trade())

        # This is where Phoenixhood will be launched if desired. There is no need to change these
        # lines, you can either remove the if or delete the whole thing depending on your purposes.
        if user_interface:
            self.launch_user_interface()
            asyncio.create_task(self.handle_queued_messages())

        await self.connect()


user_interface = True 

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


