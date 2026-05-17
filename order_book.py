"""
Eurobond Order Book — fiyat-zaman öncelikli (price-time priority) eşleştirme motoru.

Her tahvil için ayrı bir OrderBook instance'ı tutulur.
Heap'ler lazy deletion ile temizlenir (stale girişler match sırasında atlanır).
"""
import heapq
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import uuid

from models import Order, OrderSide, OrderType, OrderStatus, Trade


class OrderBook:
    def __init__(self, bond_isin: str):
        self.bond_isin = bond_isin
        # Min-heap: (neg_price, timestamp_float, order_id)  → en yüksek fiyat önce gelir
        self._bids: List[Tuple] = []
        # Min-heap: (price_float, timestamp_float, order_id) → en düşük fiyat önce gelir
        self._asks: List[Tuple] = []
        self._orders: Dict[str, Order] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_order(self, order: Order) -> List[Trade]:
        self._orders[order.id] = order
        if order.order_type == OrderType.MARKET:
            return self._match_market(order)
        return self._match_limit(order)

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.status in (OrderStatus.PENDING, OrderStatus.PARTIAL):
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.utcnow()
            return True
        return False

    def get_bids(self, depth: int = 10) -> List[Tuple[Decimal, int]]:
        """Aktif alış seviyelerini (fiyat azalan, miktar) döndürür."""
        levels: Dict[Decimal, int] = {}
        for neg_price, _, oid in self._bids:
            o = self._orders.get(oid)
            if o and o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                price = Decimal(str(-neg_price))
                levels[price] = levels.get(price, 0) + (o.quantity - o.filled_quantity)
        return sorted(levels.items(), reverse=True)[:depth]

    def get_asks(self, depth: int = 10) -> List[Tuple[Decimal, int]]:
        """Aktif satış seviyelerini (fiyat artan, miktar) döndürür."""
        levels: Dict[Decimal, int] = {}
        for price_f, _, oid in self._asks:
            o = self._orders.get(oid)
            if o and o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                price = Decimal(str(price_f))
                levels[price] = levels.get(price, 0) + (o.quantity - o.filled_quantity)
        return sorted(levels.items())[:depth]

    def get_best_bid(self) -> Optional[Decimal]:
        bids = self.get_bids(1)
        return bids[0][0] if bids else None

    def get_best_ask(self) -> Optional[Decimal]:
        asks = self.get_asks(1)
        return asks[0][0] if asks else None

    def get_spread(self) -> Optional[Decimal]:
        bb, ba = self.get_best_bid(), self.get_best_ask()
        return (ba - bb) if bb and ba else None

    # ------------------------------------------------------------------
    # Internal matching
    # ------------------------------------------------------------------

    def _match_market(self, order: Order) -> List[Trade]:
        trades: List[Trade] = []
        if order.side == OrderSide.BUY:
            trades = self._consume_asks(order)
        else:
            trades = self._consume_bids(order)
        # Doldurulamayan kısım iptal edilir
        if order.status not in (OrderStatus.FILLED,):
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.utcnow()
        return trades

    def _match_limit(self, order: Order) -> List[Trade]:
        trades: List[Trade] = []
        if order.side == OrderSide.BUY:
            trades = self._consume_asks(order, limit_price=order.price)
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                ts = order.created_at.timestamp()
                heapq.heappush(self._bids, (-float(order.price), ts, order.id))
        else:
            trades = self._consume_bids(order, limit_price=order.price)
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                ts = order.created_at.timestamp()
                heapq.heappush(self._asks, (float(order.price), ts, order.id))
        return trades

    def _consume_asks(self, buy_order: Order, limit_price: Optional[Decimal] = None) -> List[Trade]:
        trades: List[Trade] = []
        while self._asks and buy_order.filled_quantity < buy_order.quantity:
            _, _, oid = self._asks[0]
            ask = self._orders.get(oid)

            # Stale giriş → at
            if ask is None or ask.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                heapq.heappop(self._asks)
                continue

            # Fiyat kontrolü (limit buy için: ask fiyatı ≤ limit)
            if limit_price is not None and ask.price > limit_price:
                break

            qty = min(
                buy_order.quantity - buy_order.filled_quantity,
                ask.quantity - ask.filled_quantity,
            )
            trade = self._execute(buy_order, ask, qty, ask.price)  # maker fiyatı
            trades.append(trade)

            if ask.filled_quantity >= ask.quantity:
                heapq.heappop(self._asks)

        return trades

    def _consume_bids(self, sell_order: Order, limit_price: Optional[Decimal] = None) -> List[Trade]:
        trades: List[Trade] = []
        while self._bids and sell_order.filled_quantity < sell_order.quantity:
            _, _, oid = self._bids[0]
            bid = self._orders.get(oid)

            if bid is None or bid.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                heapq.heappop(self._bids)
                continue

            # Fiyat kontrolü (limit sell için: bid fiyatı ≥ limit)
            if limit_price is not None and bid.price < limit_price:
                break

            qty = min(
                sell_order.quantity - sell_order.filled_quantity,
                bid.quantity - bid.filled_quantity,
            )
            trade = self._execute(bid, sell_order, qty, bid.price)  # maker fiyatı
            trades.append(trade)

            if bid.filled_quantity >= bid.quantity:
                heapq.heappop(self._bids)

        return trades

    def _execute(self, buy_order: Order, sell_order: Order, quantity: int, price: Decimal) -> Trade:
        now = datetime.utcnow()
        for order in (buy_order, sell_order):
            order.filled_quantity += quantity
            order.status = (
                OrderStatus.FILLED if order.filled_quantity >= order.quantity
                else OrderStatus.PARTIAL
            )
            order.updated_at = now

        return Trade(
            id=str(uuid.uuid4()),
            bond_isin=self.bond_isin,
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            buyer_id=buy_order.user_id,
            seller_id=sell_order.user_id,
            price=price,
            quantity=quantity,
            executed_at=now,
        )
