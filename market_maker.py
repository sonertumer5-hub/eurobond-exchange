"""
Market Simulator — rastgele emirler ekler/çıkarır, bazen match gerçekleşir.
Çalıştır: python3 market_maker.py
"""
import urllib.request, urllib.error, json, time, random, signal, sys

API  = "http://localhost:8000"
ISIN = "US900123CT57"
MID  = 98.625   # referans orta fiyat

def post(path, data):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return None
    except Exception:
        return None

def delete(path):
    req = urllib.request.Request(f"{API}{path}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except:
        return None

def get(path):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=5) as r:
            return json.loads(r.read())
    except:
        return None

# ── Kurulum: 5 farklı trader oluştur ──
def setup():
    traders = []
    names = ["Alpha Fund", "Beta Capital", "Gamma Trading", "Delta AM", "Omega Bank"]
    for name in names:
        u = post("/users", {"name": name, "initial_cash": "999999999"})
        post(f"/users/{u['id']}/deposit-bonds", {"bond_isin": ISIN, "quantity": 99999})
        traders.append(u["id"])
        print(f"  ✓ {name} ({u['id'][:8]})")
    return traders

def pending_orders(user_id):
    orders = get(f"/users/{user_id}/orders") or []
    return [o for o in orders if o["status"] in ("pending", "partial")]

def get_orderbook():
    return get(f"/bonds/{ISIN}/orderbook?depth=20") or {"bids": [], "asks": [], "best_bid": None, "best_ask": None}

# ── Bir tur ──
def run_cycle(traders, cycle):
    ob = get_orderbook()
    best_bid = float(ob["best_bid"]) if ob["best_bid"] else MID - 0.5
    best_ask = float(ob["best_ask"]) if ob["best_ask"] else MID + 0.5

    added = 0
    cancelled = 0
    matched = 0

    # ── 1. Rastgele 3-6 emir iptal et ──
    n_cancel = random.randint(3, 6)
    cancel_targets = random.sample(traders, min(n_cancel, len(traders)))
    for uid in cancel_targets:
        orders = pending_orders(uid)
        if orders:
            victim = random.choice(orders)
            if delete(f"/users/{uid}/orders/{victim['id']}"):
                cancelled += 1

    # ── 2. Rastgele 4-7 pasif limit emir ekle (spread dışında) ──
    n_passive = random.randint(4, 7)
    for _ in range(n_passive):
        uid = random.choice(traders)
        side = random.choice(["buy", "sell"])
        qty = random.randint(5, 150)

        if side == "buy":
            # Best bid'e yakın ama altında — pasif, eşleşmez
            price = round(best_bid - random.uniform(0.05, 0.80), 2)
            price = max(price, 90.0)
        else:
            # Best ask'e yakın ama üstünde — pasif, eşleşmez
            price = round(best_ask + random.uniform(0.05, 0.80), 2)
            price = min(price, 110.0)

        r = post(f"/users/{uid}/orders", {
            "bond_isin": ISIN, "side": side,
            "order_type": "limit", "quantity": qty, "price": str(price)
        })
        if r: added += 1

    # ob'u güncelle — pasif emirler eklendikten sonra
    ob = get_orderbook()
    best_bid = float(ob["best_bid"]) if ob["best_bid"] else MID - 0.5
    best_ask = float(ob["best_ask"]) if ob["best_ask"] else MID + 0.5

    # ── 3. %50 ihtimalle agresif emir — spread'i geçer, match olur ──
    if random.random() < 0.50:
        uid = random.choice(traders)
        qty = random.randint(10, 80)
        side = random.choice(["buy", "sell"])

        if side == "buy" and ob["asks"]:
            # En iyi ask'ten biraz yukarı fiyatla al → match garantili
            price = round(best_ask + random.uniform(0.0, 0.30), 2)
            r = post(f"/users/{uid}/orders", {
                "bond_isin": ISIN, "side": "buy",
                "order_type": "limit", "quantity": qty, "price": str(price)
            })
            if r and r.get("trades"):
                matched += len(r["trades"])
                added += 1
        elif side == "sell" and ob["bids"]:
            # En iyi bid'den biraz aşağı fiyatla sat → match garantili
            price = round(best_bid - random.uniform(0.0, 0.30), 2)
            r = post(f"/users/{uid}/orders", {
                "bond_isin": ISIN, "side": "sell",
                "order_type": "limit", "quantity": qty, "price": str(price)
            })
            if r and r.get("trades"):
                matched += len(r["trades"])
                added += 1

    # ── 4. %25 ihtimalle market emir — her zaman match olur ──
    if random.random() < 0.25:
        uid = random.choice(traders)
        qty = random.randint(5, 40)
        side = random.choice(["buy", "sell"])
        if (side == "buy" and ob["asks"]) or (side == "sell" and ob["bids"]):
            r = post(f"/users/{uid}/orders", {
                "bond_isin": ISIN, "side": side,
                "order_type": "market", "quantity": qty,
            })
            if r and r.get("trades"):
                matched += len(r["trades"])

    ob2 = get_orderbook()
    b2 = ob2["best_bid"] or "—"
    a2 = ob2["best_ask"] or "—"
    spread2 = ob2["spread"] or "—"
    tag = f"  🔥 {matched} MATCH!" if matched else ""
    print(f"[{cycle:03d}] +{added} emir  -{cancelled} iptal  bid={b2}  ask={a2}  spread={spread2}{tag}")

# ── Ana döngü ──
def main():
    print("=" * 58)
    print("  Eurobond Market Simulator")
    print("  Her 3 sn: emir ekle/çıkar, bazen match gerçekleşir")
    print("  Çıkmak için Ctrl+C")
    print("=" * 58)
    print("\nTrader'lar kuruluyor...")
    traders = setup()
    print(f"\n{len(traders)} trader hazır.\n")

    cycle = 0
    def handle_sigint(sig, frame):
        print("\nSimülatör durduruldu.")
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_sigint)

    while True:
        cycle += 1
        try:
            run_cycle(traders, cycle)
        except Exception as e:
            print(f"[{cycle:03d}] Hata: {e}")
        time.sleep(3)

if __name__ == "__main__":
    main()
