from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional
import uuid


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Bond:
    isin: str
    issuer: str
    coupon_rate: float          # Yıllık kupon oranı (%)
    maturity_date: str          # Vade tarihi (YYYY-MM-DD)
    face_value: Decimal         # Nominal değer
    currency: str = "USD"


@dataclass
class Order:
    id: str
    user_id: str
    bond_isin: str
    side: OrderSide
    order_type: OrderType
    quantity: int               # Nominal adet (lot = 1000 USD face value)
    price: Optional[Decimal]    # Clean price (% of face value), market orders için None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Trade:
    id: str
    bond_isin: str
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str
    price: Decimal              # İşlem fiyatı (% of face value)
    quantity: int
    executed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class User:
    id: str
    name: str
    cash_balance: Decimal
    holdings: Dict[str, int] = field(default_factory=dict)          # {isin: quantity}
    reserved_cash: Decimal = field(default_factory=lambda: Decimal("0"))
    reserved_bonds: Dict[str, int] = field(default_factory=dict)    # {isin: quantity}
