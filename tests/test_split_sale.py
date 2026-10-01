import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();",
    "window.__t={state:function(){return state;},setTab:setTab,render:render,debt:jonDebtAllocation,"
    "balance:computeBalance,ownerProfit:ownerRealProfit,saleProfit:saleProfit,allocate:allocateSales}; boot();", 1)
(root / "_split_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8831", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
lucario = next(p for p in data["products"] if "lucario" in p["name"].lower())


def seed(pg, sales, products=None, batches=None, settlements=None):
    pg.evaluate("""(d) => {
      const S = window.__t.state();
      S.products = d.products; S.batches = d.batches; S.sales = d.sales; S.settlements = d.settlements;
      window.__t.render();
    }""", {"products": products or data["products"], "batches": batches or [], "sales": sales, "settlements": settlements or []})


try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8831/_split_copy.html#sales"); pg.wait_for_timeout(1200)

        # ---- Jon's exact reported case: he has 1 unit left, Jax has 1 left, one buyer orders both
        # in a single sale. allocateSales must produce a real split, never dump the whole order on
        # whoever has more left, and never leave the other person with nothing for no reason.
        alloc = pg.evaluate("([s,u]) => window.__t.allocate(s.map(x => Object.assign({ownerSource:'auto', lifecycleStatus:'pending'}, x)), u)",
                             [[{"id": "both", "netProfit": 100.0, "quantitySold": 2}], {"Jon": 1, "Jax": 1}])
        print("1+1, one buyer takes both -- real split, not all-or-nothing:", alloc)

        # ---- a 3-unit order when Jon has 2 left and Jax has 1 left -- splits 2/1, matching exactly
        alloc2 = pg.evaluate("([s,u]) => window.__t.allocate(s.map(x => Object.assign({ownerSource:'auto', lifecycleStatus:'pending'}, x)), u)",
                              [[{"id": "three", "netProfit": 150.0, "quantitySold": 3}], {"Jon": 2, "Jax": 1}])
        print("3-unit order, Jon has 2 left Jax has 1 left -- splits 2/1:", alloc2)

        # ---- the money math itself: a real split sale, completed and paid out, $100 total for 2
        # units, Jon has 1 and Jax has 1 -- so Jon's own share of the debt/balance/profit math must
        # be exactly $50, not $100 (the whole thing) and not $0 (nothing, like the live bug did)
        split_sale = {"id": "splitorder", "productId": lucario["id"], "netProfit": 100.0, "quantitySold": 2,
                      "ownerSource": "auto", "lifecycleStatus": "completed", "attributedTo": None,
                      "splitQty": {"Jon": 1, "Jax": 1}, "buyerName": "bothbuyer", "saleDate": "2026-09-01",
                      "createdAt": 1, "orderNumber": "split-1"}
        seed(pg, [split_sale])
        bal = pg.evaluate("window.__t.balance()")
        debt = pg.evaluate("window.__t.debt()")
        combined_profit = pg.evaluate("(id) => window.__t.saleProfit(window.__t.state().sales.find(s => s.id === id))", "splitorder")
        print("computeBalance() counts only Jon's $50 half, not the full $100:", bal)
        print("jonDebtAllocation() has exactly one row, Jon's $50 share:", [(r["owedAmount"], r["status"]) for r in debt["rows"]])
        print("saleProfit() with no cost logged yet is null (nothing priced):", combined_profit)

        # ---- now price it: Jon's unit cost $10, Jax's unit cost $30 -- different costs, since each
        # owner's half was bought with their OWN money, from their OWN purchase
        batches = [
            {"id": "bj", "productId": lucario["id"], "owner": "Jon", "quantity": 1, "unitCost": 10, "costKnown": True, "createdAt": 1},
            {"id": "bx", "productId": lucario["id"], "owner": "Jax", "quantity": 1, "unitCost": 30, "costKnown": True, "createdAt": 1},
        ]
        seed(pg, [split_sale], batches=batches)
        combined_profit2 = pg.evaluate("(id) => window.__t.saleProfit(window.__t.state().sales.find(s => s.id === id))", "splitorder")
        jon_profit2 = pg.evaluate("window.__t.ownerProfit('Jon')")
        jax_profit2 = pg.evaluate("window.__t.ownerProfit('Jax')")
        print("priced: combined profit $100 payout - ($10+$30) cost = $60:", combined_profit2)
        print("priced: Jon's own share is $50 payout - $10 cost = $40:", jon_profit2)
        print("priced: Jax's own share is $50 payout - $30 cost = $20:", jax_profit2)

        # ---- the live self-check banner: must stay silent, the identity still has to hold with a
        # split sale in the mix, same as it does for an ordinary one
        print("ledger reconciles with a split sale present:", pg.evaluate("""() => {
          const d = window.__t.debt(), bal = window.__t.balance();
          const owed = d.rows.reduce((a,r) => a + r.owedAmount, 0);
          return Math.abs(Math.round((owed - d.unallocated)*100)/100 - Math.round(bal*100)/100) < 0.01;
        }"""))

        # ---- the end-to-end UI flow: Jon's exact reported scenario through the real "Custom" form
        # -- one 2-unit sale, Jon=1/Jax=1 -- must render the split pill and actually write splitQty,
        # with a batch created for BOTH owners, not collapse to one owner like the live bug did
        group_sales = [
            {"id": "s2", "productId": lucario["id"], "netProfit": 100.0, "quantitySold": 2, "ownerSource": "auto",
             "lifecycleStatus": "pending", "attributedTo": None, "buyerName": "bothbuyer2", "saleDate": "2026-09-02", "createdAt": 2},
        ]
        seed(pg, group_sales, batches=[])
        pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(400)
        pg.click("#ownerBanner .owner-queue-row:has-text('Lucario') >> text=Custom"); pg.wait_for_timeout(300)
        pg.fill("#f_bj", "1"); pg.fill("#f_bx", "1")
        pg.click("button[data-action='submit-bought']"); pg.wait_for_timeout(300)
        print("preview shows the split pill on the 2-unit sale:", pg.locator(".confirm-row .badge.owner-split").count())
        print("preview split pill text:", pg.inner_text(".confirm-row .badge.owner-split") if pg.locator(".badge.owner-split").count() else None)
        pg.click("button[data-action='confirm-purchase']"); pg.wait_for_timeout(500)
        saved = pg.evaluate("() => window.__t.state().sales.map(s => [s.id, s.attributedTo, s.splitQty])")
        batches_after = pg.evaluate("(pid) => window.__t.state().batches.filter(b => b.productId === pid).map(b => [b.owner, b.quantity])", lucario["id"])
        print("saved sale -- real splitQty, not collapsed to one owner:", saved)
        print("a batch created for EACH owner (not just one):", sorted(batches_after))
        print("the main Sales list itself shows the split pill, not 'Unassigned':", pg.locator(".sales-list .badge.owner-split").count())
        print("errors:", errs, "| scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_split_copy.html").unlink(missing_ok=True)
