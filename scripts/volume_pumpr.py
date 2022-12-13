import logging
from decimal import Decimal
from typing import List
from math import ceil, floor

from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase

from hummingbot.core.clock import Clock

# TODO
# - active order deviation
# - exit cleanly with no hanging orders and unhedged positions - redefine stop?
# - create initializing method
#   - set tick size
#   - get exchange fees
# - show mid price, best bid & ask and spread in status
# - document
# - hanging order deviation
# - use margin order?
# - how to do post only? - ETA 2023


class VolumePumpr(ScriptStrategyBase):
    exchange = "binance"
    trading_pair = "BTC-BUSD"  # How to set paper trade balance?
    markets = {exchange: {trading_pair}}

    price_source = PriceType.MidPrice

    # tick_size = Decimal("0.01")
    order_amount = Decimal("0.003")  # cca. 50 USD
    bid_spread_ticks = Decimal("1")
    ask_spread_ticks = Decimal("1")
    bid_spread_bps = Decimal("0")
    ask_spread_bps = Decimal("0")
    jump_closer_deviation_bps = Decimal("0.6")

    maker_fee = Decimal("0")
    taker_fee = Decimal("0")

    @property
    def connector(self):
        return self.connectors[self.exchange]

    def on_tick(self):
        # maker_fee = build_trade_fee(self.exchange, True, "BTC", "BUSD", self.connector.get_maker_order_type(), TradeType.BUY, self.order_amount)
        # taker_fee = build_trade_fee(self.exchange, True, "BTC", "BUSD", self.connector.get_taker_order_type(), TradeType.BUY, self.order_amount)

        # self.logger().info(f"Maker fee: {self.maker_fee}\nTaker fee: {self.taker_fee}")

        if self.any_open_orders():
            self.check_deviation()
        else:
            self.create_order_pair()

    def any_open_orders(self):
        if len(self.get_active_orders(self.exchange)) > 0:
            return True
        else:
            return False

    def is_hanging_order(self):
        return len(self.get_active_orders(self.exchange)) == 1

    #
    # CREATE ORDER PAIRS
    #
    def create_order_pair(self):
        # proposal: List[OrderCandidate] = self.create_proposal()
        bid_proposal: OrderCandidate = self.create_proposal_bid()
        ask_proposal: OrderCandidate = self.create_proposal_ask()

        proposal: List[OrderCandidate] = self.adjust_proposal_pair(bid_proposal, ask_proposal)

        proposal_adjusted: List[OrderCandidate] = self.adjust_proposal_to_budget(proposal)
        for p in proposal_adjusted:
            msg = f"Side: {p.order_side}, amount: {p.amount}, price: {p.price}, percent_fee_value: {p.percent_fee_value}"
            self.log_with_clock(logging.INFO, msg)
        self.place_orders(proposal_adjusted)

    # def create_proposal(self) -> List[OrderCandidate]:
    #     best_bid_price = self.connector.get_price(self.trading_pair, False)
    #     best_ask_price = self.connector.get_price(self.trading_pair, True)
    #     tick_size = self.connector.get_order_price_quantum(self.trading_pair, best_bid_price)

    #     bid_spread = self.maker_fee + self.bid_spread_bps / 100
    #     ask_spread = self.maker_fee + self.ask_spread_bps / 100

    #     bid_price = self.connector.quantize_order_price(self.trading_pair, best_ask_price * Decimal(1 - bid_spread / 100))
    #     bid_price = (floor(bid_price / tick_size) - self.bid_spread_ticks) * tick_size

    #     ask_price = self.connector.quantize_order_price(self.trading_pair, best_ask_price * Decimal(1 + ask_spread / 100))
    #     ask_price = (ceil(ask_price / tick_size) + self.ask_spread_ticks) * tick_size

    #     if bid_price == ask_price:
    #         ask_price = (ceil(bid_price / tick_size) + 1) * tick_size

    #     buy_order = OrderCandidate(trading_pair=self.trading_pair, is_maker=True, order_type=OrderType.LIMIT,
    #                                order_side=TradeType.BUY, amount=Decimal(self.order_amount), price=bid_price)
    #     sell_order = OrderCandidate(trading_pair=self.trading_pair, is_maker=True, order_type=OrderType.LIMIT,
    #                                 order_side=TradeType.SELL, amount=Decimal(self.order_amount), price=ask_price)

    #     return [buy_order, sell_order]

    def create_proposal_ask(self, order_amount = None) -> OrderCandidate:
        if order_amount is None:
            order_amount = self.order_amount
        best_ask_price = self.connector.get_price(self.trading_pair, True)
        tick_size = self.connector.get_order_price_quantum(self.trading_pair, best_ask_price)
        ask_spread = self.maker_fee + self.ask_spread_bps / 100
        ask_price = self.connector.quantize_order_price(self.trading_pair, best_ask_price * Decimal(1 + ask_spread / 100))
        ask_price = (ceil(ask_price / tick_size) + self.ask_spread_ticks) * tick_size
        sell_order = OrderCandidate(trading_pair=self.trading_pair, is_maker=True, order_type=OrderType.LIMIT,
                                    order_side=TradeType.SELL, amount=Decimal(self.order_amount), price=ask_price)

        return sell_order

    def create_proposal_bid(self, order_amount = None) -> OrderCandidate:
        if order_amount is None:
            order_amount = self.order_amount
        best_bid_price = self.connector.get_price(self.trading_pair, False)
        tick_size = self.connector.get_order_price_quantum(self.trading_pair, best_bid_price)
        bid_spread = self.maker_fee + self.bid_spread_bps / 100
        bid_price = self.connector.quantize_order_price(self.trading_pair, best_bid_price * Decimal(1 - bid_spread / 100))
        bid_price = (floor(bid_price / tick_size) - self.bid_spread_ticks) * tick_size
        buy_order = OrderCandidate(trading_pair=self.trading_pair, is_maker=True, order_type=OrderType.LIMIT,
                                   order_side=TradeType.BUY, amount=Decimal(order_amount), price=bid_price)
        return buy_order

    def adjust_proposal_to_budget(self, proposal: List[OrderCandidate]) -> List[OrderCandidate]:
        proposal_adjusted = self.connector.budget_checker.adjust_candidates(proposal, all_or_none=True)
        return proposal_adjusted

    def adjust_proposal_pair(self, bid_proposal, ask_proposal) -> List[OrderCandidate]:
        """
        Don't let bid & ask be equal when creating a new order pair to prevent self trading
        """
        best_bid_price = self.connector.get_price(self.trading_pair, False)
        tick_size = self.connector.get_order_price_quantum(self.trading_pair, best_bid_price)
        if bid_proposal.price == ask_proposal.price:
            ask_proposal.price = (ceil(bid_proposal.price / tick_size) + 1) * tick_size
        return [bid_proposal, ask_proposal]

    def place_orders(self, proposal: List[OrderCandidate]):
        for order in proposal:
            self.place_order(connector_name=self.exchange, order=order)

    def place_order(self, connector_name: str, order: OrderCandidate):
        if order.order_side == TradeType.SELL:
            self.sell(connector_name=connector_name, trading_pair=order.trading_pair, amount=order.amount,
                      order_type=order.order_type, price=order.price)
        if order.order_side == TradeType.BUY:
            self.buy(connector_name=connector_name, trading_pair=order.trading_pair, amount=order.amount,
                     order_type=order.order_type, price=order.price)
    #
    # DEVIATION CHECKS
    #

    def check_deviation(self):
        """
        If any order has deviated more than jump_closer_deviation_bps from price, cancel it
        and create a new maker order closer to mid
        """
        mid_price = self.connector.get_price_by_type(self.trading_pair, self.price_source)
        for order in self.get_active_orders(self.exchange):
            spread_bps = round(abs(order.price - mid_price) / mid_price * 10000, 1)
            if spread_bps >= self.jump_closer_deviation_bps:
                self.logger().info(f"Order {order.client_order_id} has deviated from mid, placing order closer")
                quantity_remaining = order.quantity
                if not order.filled_quantity.is_nan():
                    quantity_remaining = order.quantity - order.filled_quantity
                # cancel order
                if order.is_buy:
                    proposal = self.create_proposal_bid(quantity_remaining)
                else:
                    proposal = self.create_proposal_ask(quantity_remaining)
                adjusted_proposal = self.connector.budget_checker.adjust_candidate(proposal, all_or_none=False)
                self.cancel(self.exchange, self.trading_pair, order.client_order_id)
                self.place_order(self.exchange, adjusted_proposal)
        return

    #
    # EVENTS
    #

    def did_fill_order(self, event: OrderFilledEvent):
        msg = (f"{event.trade_type.name} {round(event.amount, 4)} {event.trading_pair} {self.exchange} at {round(event.price, 2)}")
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)

    #
    # STATUS
    #

    def format_status(self) -> str:
        """
        Returns status of the current strategy on user balances and current active orders. This function is called
        when status command is issued. Override this function to create custom status display output.
        """
        if not self.ready_to_trade:
            return "Market connectors are not ready."
        lines = []
        warning_lines = []
        warning_lines.extend(self.network_warning(self.get_market_trading_pair_tuples()))

        # balance_df = self.get_balance_df()
        # lines.extend(["", "  Balances:"] + ["    " + line for line in balance_df.to_string(index=False).split("\n")])

        try:
            df = self.active_orders_df()
            df["Spread bps"] = df.apply(lambda x: self.get_spread_bps(x), axis=1)
            df["Δticks"] = df.apply(lambda x: self.get_dticks(x), axis=1)
            lines.extend(["", "  Orders:"] + ["    " + line for line in df.to_string(index=False).split("\n")])
        except ValueError:
            lines.extend(["", "  No active maker orders."])

        warning_lines.extend(self.balance_warning(self.get_market_trading_pair_tuples()))
        if len(warning_lines) > 0:
            lines.extend(["", "*** WARNINGS ***"] + warning_lines)
        return "\n".join(lines)

    def get_spread_bps(self, row):
        # Exchange, Market, Side, Price, Amount, Age, Spread bps
        mid_price = self.connector.get_mid_price(self.trading_pair)
        spread_bps = round(abs(Decimal(row["Price"]) - mid_price) / mid_price * 10000, 1)
        return spread_bps

    def get_dticks(self, row):
        """"
        Returns the deviance between mid price and order price in quoted asset and in ticks
        """
        price = Decimal(row["Price"])
        tick_size = self.connector.get_order_price_quantum(self.trading_pair, price)
        mid_price = self.connector.get_mid_price(self.trading_pair)
        dticks = round(abs(price - mid_price) / tick_size)
        return dticks

    def stop(self, clock: Clock):
        self.logger().info("RECEIVED STOP")
