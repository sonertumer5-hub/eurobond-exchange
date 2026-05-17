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
            Bond("XS2345678901", "European Investment Bank",    1.875, "2030-05-15", FACE_VALUE, "EUR"),
            Bond("XS1234567890", "Germany Federal Republic",    0.000, "2032-02-15", FACE_VALUE, "EUR"),
            Bond("US900123CT57",  "Republic of Turkey",          7.625, "2029-04-26", FACE_VALUE, "USD"),
            Bond("XS1111111111", "HSBC Holdings PLC",           3.400, "2028-11-30", FACE_VALUE, "USD"),
            Bond("XS2222222222", "BNP Paribas SA",              2.875, "2031-07-10", FACE_VALUE, "EUR"),
            Bond("XS3333333333", "Goldman Sachs Group Inc",     4.250, "2027-09-15", FACE_VALUE, "USD"),
            Bond("XS4444444444", "Kingdom of Saudi Arabia",     3.625, "2033-03-04", FACE_VALUE, "USD"),
            Bond("XS5555555555", "Apple Inc",                   2.050, "2026-09-11", FACE_VALUE, "USD"),
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
