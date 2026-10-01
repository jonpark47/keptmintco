import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();",
    "window.__t={state:function(){return state;},setTab:setTab,render:render,attrCheck:attributionCheck}; boot();", 1)
(root / "_attr_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8832", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
lucario = next(p for p in data["products"] if "lucario" in p["name"].lower())


def seed(pg, sales, batches):
    pg.evaluate("""(d) => {
      const S = window.__t.state();
      S.products = d.products; S.batches = d.batches; S.sales = d.sales; S.settlements = [];
      window.__t.render();
    }""", {"products": data["products"], "batches": batches, "sales": sales})


try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8832/_attr_copy.html#overview"); pg.wait_for_timeout(1200)

        # ---- the exact Delta Reign shape: Jon bought 3, Jax bought 2 (5 total), but every sale
        # ended up attributed to Jon (8 sold against his name) while Jax's 2 sit unused. Purchased
        # (3+2=5) and sold (8... wait, make it match: 5 sold total, 8 vs 5 would be impossible) --
        # keep purchased == sold overall (5 == 5) so this is unmistakably a misattribution, not a
        # pending-purchase gap.
        batches = [
            {"id": "bj", "productId": lucario["id"], "owner": "Jon", "quantity": 3, "unitCost": 10, "costKnown": True, "createdAt": 1},
            {"id": "bx", "productId": lucario["id"], "owner": "Jax", "quantity": 2, "unitCost": 10, "costKnown": True, "createdAt": 1},
        ]
        sales = [
            {"id": "s"+str(i), "productId": lucario["id"], "netProfit": 50.0, "quantitySold": 1, "ownerSource": "auto",
             "lifecycleStatus": "pending", "attributedTo": "Jon", "buyerName": "buyer"+str(i), "saleDate": "2026-09-0"+str(i), "createdAt": i}
            for i in range(1, 6)
        ]
        seed(pg, sales, batches)
        problems = pg.evaluate("window.__t.attrCheck()")
        print("misattribution caught -- Jon over, by how many:", [(x["over"], x["off"]) for x in problems])
        print("banner text present on screen:", pg.inner_text("#ledgerBanner").replace("\n", " ")[:200] if pg.locator("#ledgerBanner .banner").count() else None)

        # ---- fix it the real way: move 2 of Jon's sales to Jax (matching his declared 2) -- the
        # check must go quiet again, same as the live fix did
        sales2 = [dict(s) for s in sales]
        sales2[0]["attributedTo"] = "Jax"; sales2[1]["attributedTo"] = "Jax"
        seed(pg, sales2, batches)
        print("clears once attribution matches purchases:", pg.evaluate("window.__t.attrCheck()"))

        # ---- NOT a false positive: Jon sold 5, only logged buying 3 (hasn't bought the rest yet).
        # Purchased (3) != sold (5) overall, so this is an ordinary "add the cost later" gap, not a
        # misattribution -- must stay silent.
        batches3 = [{"id": "bj", "productId": lucario["id"], "owner": "Jon", "quantity": 3, "unitCost": 10, "costKnown": True, "createdAt": 1}]
        seed(pg, sales, batches3)
        print("stays quiet for an ordinary not-yet-purchased gap (no matching surplus anywhere):", pg.evaluate("window.__t.attrCheck()"))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_attr_copy.html").unlink(missing_ok=True)
