import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_bd_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8817", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (390, 320):
            pg = b.new_page(viewport={"width": w, "height": 844}, has_touch=True, is_mobile=True)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8817/_bd_copy.html#sales"); pg.wait_for_timeout(1500)
            pg.evaluate("""() => { const S = window.__t.state();
              S.products=[{id:'p1',name:'One Piece x Round 1 Promo Trading Cards English COMPLETE SET with a long title that has to wrap on a phone'}];
              S.batches=[]; S.settlements=[]; S.cancelled=[]; S.expenses=[];
              S.sales=[
                {id:'s1',productId:'p1',attributedTo:'Jon',quantitySold:1,soldPrice:425,shipPaid:21.95,buyerPaid:446.95,ebayFees:63.72,feeBreakdown:{FINAL_VALUE_FEE:56.31,FINAL_VALUE_FEE_FIXED_PER_ORDER:0.4,INTERNATIONAL_FEE:7.01},labelCost:17,labelEntered:true,netProfit:366.23,saleDate:'2026-09-14',createdAt:1,lifecycleStatus:'pending',ebayShipped:true,shipCountry:'GB',buyerName:'ukbuyer'},
                {id:'s2',productId:'p1',attributedTo:'Jax',quantitySold:1,soldPrice:120,buyerPaid:126.99,ebayFees:15.5,feeBreakdown:{FINAL_VALUE_FEE:15.1,FINAL_VALUE_FEE_FIXED_PER_ORDER:0.4},netProfit:120.92,finDiff:-17,saleDate:'2026-09-15',createdAt:2,lifecycleStatus:'pending',ebayShipped:true,shipCountry:'MX',buyerName:'mxbuyer'},
                {id:'s3',productId:'p1',attributedTo:'Jon',quantitySold:1,soldPrice:50,netProfit:40,saleDate:'2026-09-16',createdAt:3,lifecycleStatus:'pending',ebayShipped:false,buyerName:'newbuyer'}];
              window.__t.render(); }""")
            pg.wait_for_timeout(300)
            def open_for(sid):
                pg.click(f"button[data-action='sale-breakdown'][data-id='{sid}']"); pg.wait_for_timeout(250)
                txt = pg.inner_text(".modal-body").replace("\n", " | ")
                ok = pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                pg.click("button[data-action='close-modal']"); pg.wait_for_timeout(150)
                return txt, ok
            t1, ok1 = open_for("s1")
            print(w, "px full detail:", t1, "| no sideways scroll:", ok1)
            t2, ok2 = open_for("s2")
            print("  differs from eBay:", t2, "|", ok2)
            t3, ok3 = open_for("s3")
            print("  no fee data yet:", t3, "|", ok3)
            print("  errors:", errs)
            pg.close()
        b.close()
finally:
    srv.terminate(); (root / "_bd_copy.html").unlink(missing_ok=True)
