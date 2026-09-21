"""Differential test of the money math: 300 random ledgers, the app's numbers checked against an independent reference
calculation written from the rules (not copied from the app):

  - a live sale belongs to Jon, Jax or nobody; cancelled orders are outside every number
  - Jax owes Jon the FULL payout of Jon's sales that eBay has released, less what Jax already paid Jon (and plus what Jon
    paid Jax); what anyone paid for items never changes what is owed
  - pending sales are shown apart and are not owed yet
  - profit = payout minus the cost of the units sold, oldest purchase first, per owner and item; a sale whose units land on an
    unpriced or missing purchase has no profit yet (it is not counted, never guessed)
"""
import json, pathlib, random, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},render:render,computeBalance:computeBalance,pendingBalance:pendingBalance,ownerProfitBreakdown:ownerProfitBreakdown,ownerRealProfit:ownerRealProfit,unitCostFor:unitCostFor}; boot();", 1)
(root / "_mp_copy.html").write_text(html, encoding="utf-8")


def nk(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def canon(products, pid):
    p = products[pid]
    for _ in range(5):
        if p.get("sameAs") and p["sameAs"] in products:
            p = products[p["sameAs"]]
        else:
            break
    return nk(p["name"])


def reference(led):
    prods = {p["id"]: p for p in led["products"]}
    live = [s for s in led["sales"]]
    bal = 0.0
    pend = 0.0
    pend_n = 0
    for s in live:
        if s.get("attributedTo") == "Jon":
            if s.get("lifecycleStatus") != "pending":
                bal += s["netProfit"]
            else:
                pend += s["netProfit"]
                pend_n += 1
    for t in led["settlements"]:
        if t["from"] == "Jax" and t["to"] == "Jon":
            bal -= t["amount"]
        elif t["from"] == "Jon" and t["to"] == "Jax":
            bal += t["amount"]
    # oldest purchase first
    pools = {}
    for b in sorted(led["batches"], key=lambda b: b["createdAt"]):
        k = (canon(prods, b["productId"]), b["owner"])
        known = (b.get("unitCost") or 0) > 0 or bool(b.get("costKnown"))
        pools.setdefault(k, []).append([b["quantity"], b["unitCost"] if known else None])
    unit = {}
    for s in sorted(live, key=lambda s: (s["saleDate"], s["createdAt"])):
        if not s.get("attributedTo"):
            unit[s["id"]] = None
            continue
        need, tot, ok = s["quantitySold"], 0.0, True
        for lot in pools.get((canon(prods, s["productId"]), s["attributedTo"]), []):
            if need <= 0:
                break
            if lot[0] <= 0:
                continue
            take = min(lot[0], need)
            lot[0] -= take
            need -= take
            if lot[1] is None:
                ok = False
            else:
                tot += take * lot[1]
        unit[s["id"]] = tot / s["quantitySold"] if ok and need <= 0 else None
    own = {}
    for who in ("Jon", "Jax"):
        avail = sum(s["netProfit"] for s in live if s.get("attributedTo") == who and s.get("lifecycleStatus") != "pending")
        pending = sum(s["netProfit"] for s in live if s.get("attributedTo") == who and s.get("lifecycleStatus") == "pending")
        known = sum(s["netProfit"] - unit[s["id"]] * s["quantitySold"] for s in live if s.get("attributedTo") == who and unit[s["id"]] is not None)
        missing = sum(1 for s in live if s.get("attributedTo") == who and unit[s["id"]] is None)
        own[who] = {"total": avail + pending, "available": avail, "pending": pending, "profit": known, "missing": missing}
    return {"balance": bal, "pending": pend, "pending_n": pend_n, "unit": unit, "own": own}


def random_ledger(rng):
    names = ["Ascended Heroes ETB", "One Piece Round 1 Set", "Zelda Controller", "Pikachu 150/128", "Mew 152/128", "Playmat"]
    products = []
    for i in range(rng.randint(2, 7)):
        base = rng.choice(names)
        products.append({"id": f"p{i}", "name": base if rng.random() < 0.6 else base + " NEW SEALED"})
    if len(products) > 2 and rng.random() < 0.4:
        products[-1]["sameAs"] = products[0]["id"]
    batches = []
    for i in range(rng.randint(0, 9)):
        known = rng.random() < 0.75
        batches.append({"id": f"b{i}", "productId": rng.choice(products)["id"], "owner": rng.choice(["Jon", "Jax"]), "quantity": rng.randint(1, 4),
                        "unitCost": round(rng.uniform(5, 120), 2) if known else 0, "costKnown": known and rng.random() < 0.9, "createdAt": rng.randint(1, 1000)})
    sales = []
    for i in range(rng.randint(0, 14)):
        sales.append({"id": f"s{i}", "productId": rng.choice(products)["id"], "attributedTo": rng.choice(["Jon", "Jax", "Jon", "Jax", None]), "quantitySold": rng.randint(1, 3),
                      "netProfit": round(rng.uniform(-20, 300), 2), "saleDate": f"2026-09-{rng.randint(1, 28):02d}", "createdAt": rng.randint(1, 1000),
                      "lifecycleStatus": rng.choice(["pending", "completed", "completed"])})
    settlements = []
    for i in range(rng.randint(0, 4)):
        a, b = rng.choice([("Jax", "Jon"), ("Jon", "Jax")])
        settlements.append({"id": f"t{i}", "from": a, "to": b, "amount": round(rng.uniform(1, 200), 2)})
    return {"products": products, "batches": batches, "sales": sales, "settlements": settlements}


srv = subprocess.Popen([sys.executable, "-m", "http.server", "8822", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8822/_mp_copy.html#overview"); pg.wait_for_timeout(1500)
        rng = random.Random(20260921)
        bad, checked = [], 0
        for n in range(300):
            led = random_ledger(rng)
            ref = reference(led)
            got = pg.evaluate("""(d) => { const S = window.__t.state(); S.products=d.products; S.batches=d.batches; S.sales=d.sales; S.settlements=d.settlements; S.cancelled=[]; S.expenses=[];
                const own = {}; ['Jon','Jax'].forEach(w => { const o = window.__t.ownerProfitBreakdown(w), r = window.__t.ownerRealProfit(w); own[w] = {total:o.total, available:o.available, pending:o.pending, profit:r.profit, missing:r.missing}; });
                const unit = {}; S.sales.forEach(s => { unit[s.id] = window.__t.unitCostFor(s); });
                const pb = window.__t.pendingBalance();
                return {balance: window.__t.computeBalance(), pending: pb.amount, pending_n: pb.count, unit, own}; }""", led)
            checked += 1
            def close(a, c):
                return (a is None and c is None) or (a is not None and c is not None and abs(a - c) < 0.005)
            probs = []
            if not close(got["balance"], ref["balance"]): probs.append(("balance", got["balance"], ref["balance"]))
            if not close(got["pending"], ref["pending"]) or got["pending_n"] != ref["pending_n"]: probs.append(("pending", got["pending"], ref["pending"]))
            for sid, u in ref["unit"].items():
                if not close(got["unit"][sid], u): probs.append(("unit cost " + sid, got["unit"][sid], u))
            for who in ("Jon", "Jax"):
                for k in ("total", "available", "pending", "profit"):
                    if not close(got["own"][who][k], ref["own"][who][k]): probs.append((who + " " + k, got["own"][who][k], ref["own"][who][k]))
                if got["own"][who]["missing"] != ref["own"][who]["missing"]: probs.append((who + " missing", got["own"][who]["missing"], ref["own"][who]["missing"]))
            # rules that must hold whatever the data
            unowned = sum(s["netProfit"] for s in led["sales"] if not s.get("attributedTo"))
            total_all = sum(s["netProfit"] for s in led["sales"])
            if abs(got["own"]["Jon"]["total"] + got["own"]["Jax"]["total"] + unowned - total_all) > 0.01: probs.append(("Jon + Jax + unassigned != all payouts", None, None))
            if probs:
                bad.append((n, probs[:3]))
        print("random ledgers checked:", checked)
        print("ledgers where the app and the reference disagree:", len(bad))
        for n, pr in bad[:5]:
            print("  ledger", n, pr)
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_mp_copy.html").unlink(missing_ok=True)
