"""
Exchange — kullanıcı yönetimi, emir yerleştirme, takas (settlement) ve sorgulama.
"""
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import uuid

from models import Bond, User, Order, Trade, OrderSide, OrderType, OrderStatus
from order_book import OrderBook


FACE_VALUE = Decimal("1000")  # 1 lot = 1000 USD/EUR nominal


class Exchange:
    def __init__(self):
        self.bonds: Dict[str, Bond] = {}
        self.users: Dict[str, User] = {}
        self.order_books: Dict[str, OrderBook] = {}
        self.trades: List[Trade] = []
        self.all_orders: Dict[str, Order] = {}
        self._seed_bonds()

    # ------------------------------------------------------------------
    # Başlangıç verileri
    # ------------------------------------------------------------------

    def _seed_bonds(self):
        sample = [
            # USD
            Bond("US900123CK49", "Türkiye Cumhuriyeti", 4.875,  "2026-10-09", FACE_VALUE, "USD"),
            Bond("US900123CL22", "Türkiye Cumhuriyeti", 6.000,  "2027-03-25", FACE_VALUE, "USD"),
            Bond("USM88269US88", "Türkiye Cumhuriyeti", 8.600,  "2027-09-24", FACE_VALUE, "USD"),
            Bond("US900123DF45", "Türkiye Cumhuriyeti", 9.875,  "2028-01-15", FACE_VALUE, "USD"),
            Bond("US900123CP36", "Türkiye Cumhuriyeti", 5.125,  "2028-02-17", FACE_VALUE, "USD"),
            Bond("US900123CQ19", "Türkiye Cumhuriyeti", 6.125,  "2028-10-24", FACE_VALUE, "USD"),
            Bond("US900123DH01", "Türkiye Cumhuriyeti", 9.375,  "2029-03-14", FACE_VALUE, "USD"),
            Bond("US900123CT57", "Türkiye Cumhuriyeti", 7.625,  "2029-04-26", FACE_VALUE, "USD"),
            Bond("US900123AL40", "Türkiye Cumhuriyeti", 11.875, "2030-01-15", FACE_VALUE, "USD"),
            Bond("US900123CY43", "Türkiye Cumhuriyeti", 5.250,  "2030-03-13", FACE_VALUE, "USD"),
            Bond("US900123DJ66", "Türkiye Cumhuriyeti", 9.125,  "2030-07-13", FACE_VALUE, "USD"),
            Bond("US900123DA57", "Türkiye Cumhuriyeti", 5.950,  "2031-01-15", FACE_VALUE, "USD"),
            Bond("US900123DV94", "Türkiye Cumhuriyeti", 6.375,  "2031-05-22", FACE_VALUE, "USD"),
            Bond("US900123DC14", "Türkiye Cumhuriyeti", 5.875,  "2031-06-26", FACE_VALUE, "USD"),
            Bond("US900123DP27", "Türkiye Cumhuriyeti", 7.125,  "2032-02-12", FACE_VALUE, "USD"),
            Bond("US900123DL13", "Türkiye Cumhuriyeti", 7.125,  "2032-07-17", FACE_VALUE, "USD"),
            Bond("US900123DG28", "Türkiye Cumhuriyeti", 9.375,  "2033-01-19", FACE_VALUE, "USD"),
            Bond("US900123DT49", "Türkiye Cumhuriyeti", 6.300,  "2033-03-14", FACE_VALUE, "USD"),
            Bond("US900123DD96", "Türkiye Cumhuriyeti", 6.500,  "2033-09-20", FACE_VALUE, "USD"),
            Bond("US900123AT75", "Türkiye Cumhuriyeti", 8.000,  "2034-02-14", FACE_VALUE, "USD"),
            Bond("US900123DK30", "Türkiye Cumhuriyeti", 7.625,  "2034-05-15", FACE_VALUE, "USD"),
            Bond("US900123DN78", "Türkiye Cumhuriyeti", 6.500,  "2035-01-03", FACE_VALUE, "USD"),
            Bond("US900123DR82", "Türkiye Cumhuriyeti", 6.950,  "2035-09-16", FACE_VALUE, "USD"),
            Bond("US900123AY60", "Türkiye Cumhuriyeti", 6.875,  "2036-03-17", FACE_VALUE, "USD"),
            Bond("US900123DS65", "Türkiye Cumhuriyeti", 6.800,  "2036-11-04", FACE_VALUE, "USD"),
            Bond("US900123DU12", "Türkiye Cumhuriyeti", 6.875,  "2038-01-14", FACE_VALUE, "USD"),
            Bond("US900123BB58", "Türkiye Cumhuriyeti", 7.250,  "2038-03-05", FACE_VALUE, "USD"),
            Bond("US900123BG46", "Türkiye Cumhuriyeti", 6.750,  "2040-05-30", FACE_VALUE, "USD"),
            Bond("US900123BJ84", "Türkiye Cumhuriyeti", 6.000,  "2041-01-14", FACE_VALUE, "USD"),
            Bond("US900123CB40", "Türkiye Cumhuriyeti", 4.875,  "2043-04-16", FACE_VALUE, "USD"),
            Bond("US900123CG37", "Türkiye Cumhuriyeti", 6.625,  "2045-02-17", FACE_VALUE, "USD"),
            Bond("US900123CM05", "Türkiye Cumhuriyeti", 5.750,  "2047-05-13", FACE_VALUE, "USD"),
            # EUR
            Bond("XS2361850527", "Türkiye Cumhuriyeti", 4.375,  "2027-07-08", FACE_VALUE, "EUR"),
            Bond("XS2790222116", "Türkiye Cumhuriyeti", 5.875,  "2030-05-21", FACE_VALUE, "EUR"),
            Bond("XS3123715297", "Türkiye Cumhuriyeti", 5.200,  "2031-08-18", FACE_VALUE, "EUR"),
            Bond("XS3293834662", "Türkiye Cumhuriyeti", 5.150,  "2034-03-10", FACE_VALUE, "EUR"),
        ]
        for b in sample:
            self.bonds[b.isin] = b
            self.order_books[b.isin] = OrderBook(b.isin)

    # ------------------------------------------------------------------
    # Kullanıcı yönetimi
    # ------------------------------------------------------------------

    def create_user(self, name: str, initial_cash: Decimal = Decimal("1_000_000")) -> User:
        user = User(id=str(uuid.uuid4()), name=name, cash_balance=initial_cash)
        self.users[user.id] = user
        return user

    def deposit_cash(self, user_id: str, amount: Decimal) -> User:
        if amount <= 0:
            raise ValueError("Miktar pozitif olmalıdır")
        user = self._user(user_id)
        user.cash_balance += amount
        return user

    def deposit_bonds(self, user_id: str, bond_isin: str, quantity: int) -> User:
        self._bond(bond_isin)
        if quantity <= 0:
            raise ValueError("Miktar pozitif olmalıdır")
        user = self._user(user_id)
        user.holdings[bond_isin] = user.holdings.get(bond_isin, 0) + quantity
        return user

    # ------------------------------------------------------------------
    # Emir yönetimi
    # ------------------------------------------------------------------

    def place_order(
        self,
        user_id: str,
        bond_isin: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: int,
        price: Optional[Decimal] = None,
    ) -> Tuple[Order, List[Trade]]:
        user = self._user(user_id)
        self._bond(bond_isin)

        if quantity <= 0:
            raise ValueError("Adet pozitif olmalıdır")
        if order_type == OrderType.LIMIT and (price is None or price <= 0):
            raise ValueError("Limit emirler için geçerli bir fiyat gereklidir")
        if order_type == OrderType.MARKET:
            price = None  # market emirlerde fiyat yok

        if side == OrderSide.BUY:
            self._reserve_cash(user, price, quantity, order_type)
        else:
            self._reserve_bonds(user, bond_isin, quantity)

        order = Order(
            id=str(uuid.uuid4()),
            user_id=user_id,
            bond_isin=bond_isin,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
        )
        self.all_orders[order.id] = order

        trades = self.order_books[bond_isin].add_order(order)
        for t in trades:
            self._settle(t)
            self.trades.append(t)

        # Market buy iptal olursa rezervi serbest bırak
        if order.status == OrderStatus.CANCELLED and side == OrderSide.BUY and order_type == OrderType.MARKET:
            pass  # market için cash rezerve edilmedi

        return order, trades

    def cancel_order(self, user_id: str, order_id: str) -> Order:
        order = self.all_orders.get(order_id)
        if not order:
            raise ValueError(f"Emir bulunamadı: {order_id}")
        if order.user_id != user_id:
            raise PermissionError("Başkasının emri iptal edilemez")
        if order.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL):
            raise ValueError(f"Bu emir iptal edilemez (durum: {order.status.value})")

        self.order_books[order.bond_isin].cancel_order(order_id)

        user = self._user(user_id)
        remaining = order.quantity - order.filled_quantity

        if order.side == OrderSide.BUY and order.price:
            release = order.price * remaining
            user.reserved_cash -= release
            user.cash_balance += release
        elif order.side == OrderSide.SELL:
            user.reserved_bonds[order.bond_isin] = (
                user.reserved_bonds.get(order.bond_isin, 0) - remaining
            )
            user.holdings[order.bond_isin] = (
                user.holdings.get(order.bond_isin, 0) + remaining
            )
        return order

    # ------------------------------------------------------------------
    # Sorgular
    # ------------------------------------------------------------------

    def get_order_book(self, bond_isin: str, depth: int = 10) -> dict:
        self._bond(bond_isin)
        ob = self.order_books[bond_isin]
        bond = self.bonds[bond_isin]
        return {
            "bond_isin": bond_isin,
            "issuer": bond.issuer,
            "currency": bond.currency,
            "bids": [{"price": str(p), "quantity": q} for p, q in ob.get_bids(depth)],
            "asks": [{"price": str(p), "quantity": q} for p, q in ob.get_asks(depth)],
            "best_bid": str(ob.get_best_bid()) if ob.get_best_bid() else None,
            "best_ask": str(ob.get_best_ask()) if ob.get_best_ask() else None,
            "spread": str(ob.get_spread()) if ob.get_spread() else None,
        }

    def get_recent_trades(self, bond_isin: Optional[str] = None, limit: int = 50) -> List[Trade]:
        result = [t for t in self.trades if not bond_isin or t.bond_isin == bond_isin]
        return result[-limit:]

    def get_user_orders(self, user_id: str) -> List[Order]:
        self._user(user_id)
        return [o for o in self.all_orders.values() if o.user_id == user_id]

    def get_portfolio(self, user_id: str) -> dict:
        user = self._user(user_id)
        return {
            "user_id": user.id,
            "name": user.name,
            "cash_balance": str(user.cash_balance),
            "reserved_cash": str(user.reserved_cash),
            "holdings": {k: v for k, v in user.holdings.items() if v > 0},
            "reserved_bonds": {k: v for k, v in user.reserved_bonds.items() if v > 0},
        }

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _user(self, user_id: str) -> User:
        u = self.users.get(user_id)
        if not u:
            raise ValueError(f"Kullanıcı bulunamadı: {user_id}")
        return u

    def _bond(self, bond_isin: str) -> Bond:
        b = self.bonds.get(bond_isin)
        if not b:
            raise ValueError(f"Tahvil bulunamadı: {bond_isin}")
        return b

    def _reserve_cash(self, user: User, price: Optional[Decimal], quantity: int, order_type: OrderType):
        if order_type == OrderType.MARKET:
            return  # market emirlerde önceden ne kadar tutacağımızı bilemeyiz
        required = price * quantity
        if user.cash_balance < required:
            raise ValueError(
                f"Yetersiz nakit. Gerekli: {required:.2f}, Mevcut: {user.cash_balance:.2f}"
            )
        user.cash_balance -= required
        user.reserved_cash += required

    def _reserve_bonds(self, user: User, bond_isin: str, quantity: int):
        available = user.holdings.get(bond_isin, 0)
        if available < quantity:
            raise ValueError(
                f"Yetersiz tahvil. Gerekli: {quantity}, Mevcut: {available}"
            )
        user.holdings[bond_isin] -= quantity
        user.reserved_bonds[bond_isin] = user.reserved_bonds.get(bond_isin, 0) + quantity

    def _settle(self, trade: Trade):
        buyer = self._user(trade.buyer_id)
        seller = self._user(trade.seller_id)
        value = trade.price * trade.quantity

        # Alıcı: rezerve nakit → tahvil
        buyer.reserved_cash -= value
        buyer.holdings[trade.bond_isin] = buyer.holdings.get(trade.bond_isin, 0) + trade.quantity

        # Satıcı: rezerve tahvil → nakit
        seller.reserved_bonds[trade.bond_isin] = (
            seller.reserved_bonds.get(trade.bond_isin, 0) - trade.quantity
        )
        seller.cash_balance += value
