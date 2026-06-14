"""
Eurobond Exchange — FastAPI REST API

Başlatmak için:
    pip install fastapi uvicorn
    uvicorn main:app --reload

Dokümantasyon: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import List, Optional
import random
import threading
import time

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from exchange import Exchange
from models import OrderSide, OrderType, OrderStatus

exchange = Exchange()

# ── Market Maker (background thread) ─────────────────────────────────────────

ISIN = "US900123CT57"
MID  = 98.625

def _mm_setup():
    traders = []
    names = ["Alpha Fund", "Beta Capital", "Gamma Trading", "Delta AM", "Omega Bank"]
    for name in names:
        user = exchange.create_user(name, Decimal("999999999"))
        exchange.deposit_bonds(user.id, ISIN, 99999)
        traders.append(user.id)
    return traders

def _mm_pending(user_id):
    return [o for o in exchange.get_user_orders(user_id)
            if o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL)]

def _mm_cycle(traders):
    try:
        ob = exchange.get_order_book(ISIN, 20)
        best_bid = float(ob["best_bid"]) if ob["best_bid"] else MID - 0.5
        best_ask = float(ob["best_ask"]) if ob["best_ask"] else MID + 0.5

        # İptal
        for uid in random.sample(traders, min(random.randint(3, 6), len(traders))):
            orders = _mm_pending(uid)
            if orders:
                victim = random.choice(orders)
                try:
                    exchange.cancel_order(uid, victim.id)
                except Exception:
                    pass

        # Pasif limitler
        for _ in range(random.randint(4, 7)):
            uid = random.choice(traders)
            side = random.choice(["buy", "sell"])
            qty  = random.randint(5, 150)
            if side == "buy":
                price = Decimal(str(round(max(best_bid - random.uniform(0.05, 0.80), 90.0), 2)))
            else:
                price = Decimal(str(round(min(best_ask + random.uniform(0.05, 0.80), 110.0), 2)))
            try:
                exchange.place_order(uid, ISIN, OrderSide(side), OrderType.LIMIT, qty, price)
            except Exception:
                pass

        # OB güncelle
        ob = exchange.get_order_book(ISIN, 20)
        best_bid = float(ob["best_bid"]) if ob["best_bid"] else MID - 0.5
        best_ask = float(ob["best_ask"]) if ob["best_ask"] else MID + 0.5

        # Agresif limit (%50)
        if random.random() < 0.50:
            uid  = random.choice(traders)
            qty  = random.randint(10, 80)
            side = random.choice(["buy", "sell"])
            if side == "buy" and ob["asks"]:
                price = Decimal(str(round(best_ask + random.uniform(0.0, 0.30), 2)))
                try:
                    exchange.place_order(uid, ISIN, OrderSide.BUY, OrderType.LIMIT, qty, price)
                except Exception:
                    pass
            elif side == "sell" and ob["bids"]:
                price = Decimal(str(round(best_bid - random.uniform(0.0, 0.30), 2)))
                try:
                    exchange.place_order(uid, ISIN, OrderSide.SELL, OrderType.LIMIT, qty, price)
                except Exception:
                    pass

        # Market emir (%25)
        if random.random() < 0.25:
            uid  = random.choice(traders)
            qty  = random.randint(5, 40)
            side = random.choice(["buy", "sell"])
            if (side == "buy" and ob["asks"]) or (side == "sell" and ob["bids"]):
                try:
                    exchange.place_order(uid, ISIN, OrderSide(side), OrderType.MARKET, qty)
                except Exception:
                    pass
    except Exception:
        pass

def _mm_run():
    time.sleep(5)
    traders = _mm_setup()
    while True:
        _mm_cycle(traders)
        time.sleep(3)

@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=_mm_run, daemon=True)
    t.start()
    yield

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Eurobond Exchange API",
    description="Kullanıcılar arası karşılıklı eurobond alım-satım platformu (order book tabanlı)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Request/Response şemaları
# ===========================================================================

class CreateUserReq(BaseModel):
    name: str
    initial_cash: Decimal = Decimal("1000000")

class DepositCashReq(BaseModel):
    amount: Decimal

class DepositBondsReq(BaseModel):
    bond_isin: str
    quantity: int

class PlaceOrderReq(BaseModel):
    bond_isin: str
    side: str           # "buy" | "sell"
    order_type: str     # "limit" | "market"
    quantity: int
    price: Optional[Decimal] = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, v):
        if v not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return v

    @field_validator("order_type")
    @classmethod
    def validate_type(cls, v):
        if v not in ("limit", "market"):
            raise ValueError("order_type must be 'limit' or 'market'")
        return v


# ===========================================================================
# Yardımcı fonksiyonlar
# ===========================================================================

def _order_dict(o):
    return {
        "id": o.id,
        "bond_isin": o.bond_isin,
        "side": o.side.value,
        "type": o.order_type.value,
        "quantity": o.quantity,
        "price": str(o.price) if o.price else None,
        "status": o.status.value,
        "filled_quantity": o.filled_quantity,
        "created_at": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
    }

def _trade_dict(t):
    return {
        "id": t.id,
        "bond_isin": t.bond_isin,
        "price": str(t.price),
        "quantity": t.quantity,
        "buyer_id": t.buyer_id,
        "seller_id": t.seller_id,
        "executed_at": t.executed_at.isoformat(),
    }


# ===========================================================================
# Endpoint'ler
# ===========================================================================

@app.get("/", response_class=FileResponse, tags=["Info"])
def root():
    return FileResponse("frontend.html")

@app.get("/calculator", response_class=FileResponse, tags=["Info"])
def calculator():
    return FileResponse("calculator.html")

@app.get("/api", tags=["Info"])
def api_info():
    return {"service": "Eurobond Exchange", "version": "1.0.0", "docs": "/docs"}


# --- Tahviller ---

@app.get("/bonds", tags=["Bonds"])
def list_bonds():
    """Borsada işlem gören tüm eurobond'ları listeler."""
    return [
        {
            "isin": b.isin,
            "issuer": b.issuer,
            "coupon_rate": b.coupon_rate,
            "maturity_date": b.maturity_date,
            "face_value": str(b.face_value),
            "currency": b.currency,
        }
        for b in exchange.bonds.values()
    ]


@app.get("/bonds/{isin}/orderbook", tags=["Order Book"])
def get_order_book(
    isin: str = Path(..., description="Tahvil ISIN kodu"),
    depth: int = Query(10, ge=1, le=50, description="Her taraftaki seviye sayısı"),
):
    """Belirli bir tahvilin emir defterini (order book) döndürür."""
    try:
        return exchange.get_order_book(isin, depth)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/bonds/{isin}/trades", tags=["Trades"])
def get_bond_trades(
    isin: str = Path(..., description="Tahvil ISIN kodu"),
    limit: int = Query(50, ge=1, le=200),
):
    """Belirli bir tahvilin gerçekleşmiş işlem geçmişini döndürür."""
    try:
        return [_trade_dict(t) for t in exchange.get_recent_trades(isin, limit)]
    except ValueError as e:
        raise HTTPException(404, str(e))


# --- Kullanıcılar ---

@app.post("/users", tags=["Users"], status_code=201)
def create_user(req: CreateUserReq):
    """Yeni bir kullanıcı oluşturur."""
    user = exchange.create_user(req.name, req.initial_cash)
    return {"id": user.id, "name": user.name, "cash_balance": str(user.cash_balance)}


@app.get("/users/{user_id}/portfolio", tags=["Users"])
def get_portfolio(user_id: str):
    """Kullanıcının nakit ve tahvil portföyünü döndürür."""
    try:
        return exchange.get_portfolio(user_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/users/{user_id}/deposit-cash", tags=["Users"])
def deposit_cash(user_id: str, req: DepositCashReq):
    """Kullanıcı hesabına nakit ekler."""
    try:
        user = exchange.deposit_cash(user_id, req.amount)
        return {"cash_balance": str(user.cash_balance)}
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.post("/users/{user_id}/deposit-bonds", tags=["Users"])
def deposit_bonds(user_id: str, req: DepositBondsReq):
    """Kullanıcı hesabına tahvil ekler (dışarıdan tahvil getirme)."""
    try:
        user = exchange.deposit_bonds(user_id, req.bond_isin, req.quantity)
        return {"holdings": user.holdings}
    except ValueError as e:
        raise HTTPException(400, str(e))


# --- Emirler ---

@app.post("/users/{user_id}/orders", tags=["Orders"])
def place_order(user_id: str, req: PlaceOrderReq):
    """
    Yeni emir girer. Limit veya market emir olabilir.

    - **limit**: Belirtilen fiyat veya daha iyi fiyattan işlem yapar, dolmazsa order book'ta bekler.
    - **market**: Mevcut en iyi karşı fiyattan anında işlem yapar.

    Fiyat, tahvilin nominal değerinin yüzdesi olarak girilir (örn: 98.50 = %98.50).
    """
    try:
        order, trades = exchange.place_order(
            user_id=user_id,
            bond_isin=req.bond_isin,
            side=OrderSide(req.side),
            order_type=OrderType(req.order_type),
            quantity=req.quantity,
            price=req.price,
        )
        return {"order": _order_dict(order), "trades": [_trade_dict(t) for t in trades]}
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))


@app.delete("/users/{user_id}/orders/{order_id}", tags=["Orders"])
def cancel_order(user_id: str, order_id: str):
    """Bekleyen bir emri iptal eder."""
    try:
        order = exchange.cancel_order(user_id, order_id)
        return {"id": order.id, "status": order.status.value, "message": "Emir iptal edildi"}
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))


@app.get("/users/{user_id}/orders", tags=["Orders"])
def get_user_orders(user_id: str):
    """Kullanıcının tüm emirlerini listeler."""
    try:
        return [_order_dict(o) for o in exchange.get_user_orders(user_id)]
    except ValueError as e:
        raise HTTPException(404, str(e))


# --- Tüm işlemler ---

@app.get("/trades", tags=["Trades"])
def get_all_trades(limit: int = Query(50, ge=1, le=200)):
    """Tüm tahvillerdeki son gerçekleşmiş işlemleri döndürür."""
    return [_trade_dict(t) for t in exchange.get_recent_trades(limit=limit)]


# ===========================================================================
# Çalıştırma
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
