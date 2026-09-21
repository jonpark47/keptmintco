import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_cx_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8819", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (390, 320):
            pg = b.new_page(viewport={"width": w, "height": 844}, has_touch=True, is_mobile=True)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8819/_cx_copy.html#sales"); pg.wait_for_timeout(1500)
            pg.evaluate("""() => { const S = window.__t.state();
              S.products=[{id:'p1',name:'Round 1 x One Piece Collab Club Card Nami and Robin LOADED With $200 In Credits'},{id:'p2',name:'Live item'}];
              S.batches=[]; S.settlements=[]; S.expenses=[];
              S.sales=[{id:'s1',productId:'p2',attributedTo:'Jon',quantitySold:1,netProfit:80,saleDate:'2026-09-19',createdAt:3,lifecycleStatus:'pending',buyerName:'livebuyer'}];
              S.cancelled=[{id:'c1',productId:'p1',attributedTo:'Jon',quantitySold:1,netProfit:69.64,saleDate:'2026-09-21',createdAt:5,orderState:'cancelled',buyerName:'tbt_vending',cancelNet:0},
                           {id:'c2',productId:'p1',attributedTo:'Jon',quantitySold:1,netProfit:134.44,saleDate:'2026-09-20',createdAt:4,orderState:'cancelled',buyerName:'tbt_vending',cancelNet:-6.99},
                           {id:'c3',productId:'p1',attributedTo:'Jon',quantitySold:1,netProfit:50,saleDate:'2026-09-18',createdAt:2,orderState:'cancelled',buyerName:'nofin'}];
              window.__t.render(); }""")
            pg.wait_for_timeout(300)
            rows = pg.locator(".sale-row")
            print(w, "px, rows in the main list:", rows.count(), "| cancelled rows:", pg.locator(".sale-row.cancelled").count())
            print("  red Cancelled badges:", pg.locator(".sale-row.cancelled .badge.cancel-red", has_text="Cancelled").count())
            print("  net notes:", [t.replace("\n", " ") for t in pg.locator(".sale-row.cancelled .sale-tags").all_inner_texts()])
            print("  chip All count:", pg.locator(".fchip.on").first.inner_text().replace("\n", " "))
            print("  totals unchanged by cancelled ones:", pg.locator(".tiles.mini .tile").first.inner_text().replace("\n", " | "))
            print("  no sideways scroll:", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "| errors:", errs)
            pg.close()
        b.close()
finally:
    srv.terminate(); (root / "_cx_copy.html").unlink(missing_ok=True)
