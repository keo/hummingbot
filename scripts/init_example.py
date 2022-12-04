from hummingbot.strategy.script_strategy_base import ScriptStrategyBase

import json

class InitialExample(ScriptStrategyBase):
    markets = {"binance_paper_trade": {"ETH-USDT"}}

    def on_tick(self):
        self.logger().info("First Script!")
        conn = self.connectors["binance_paper_trade"]
        best_bid = conn.get_price("ETH-USDT", False)
        best_ask = conn.get_price("ETH-USDT", True)
        self.logger().info(f'ASK: {best_ask}')
        self.logger().info(f'BID: {best_bid}')
        
        volume = 10
        self.logger().info(f'Price for volume of {volume} is {conn.get_price_for_volume("ETH-USDT", True, volume).result_price}')
        
        volume = 100
        self.logger().info(f'Price for volume of {volume} is {conn.get_price_for_volume("ETH-USDT", True, volume).result_price}')
        
        volume = 1000
        self.logger().info(f'Price for volume of {volume} is {conn.get_price_for_volume("ETH-USDT", True, volume).result_price}')
        