import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render,unitCostFor:unitCostFor}; boot();", 1)
(root / "_eo_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8812", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8812/_eo_copy.html#sales"); pg.wait_for_timeout(1500)
        pg.evaluate("""() => { const S = window.__t.state();
          S.products=[{id:'p1',name:'Test Item One'}];
          S.sales=[{id:'s1',productId:'p1',attributedTo:'Jon',quantitySold:1,netProfit:80,saleDate:'2026-09-01',createdAt:1,lifecycleStatus:'pending'},
                   {id:'s2',productId:'p1',attributedTo:'Jon',quantitySold:1,netProfit:null,saleDate:'2026-09-02',createdAt:2,lifecycleStatus:'pending'}];
          S.batches=[{id:'b1',productId:'p1',owner:'Jon',quantity:1,unitCost:30,costKnown:true,sourceSaleId:'s1',status:'preorder',createdAt:1},
                     {id:'b2',productId:'p1',owner:'Jon',quantity:1,unitCost:0,costKnown:false,sourceSaleId:'s2',status:'preorder',createdAt:2}];
          S.settlements=[]; S.cancelled=[]; window.__t.render(); }""")
        pg.wait_for_timeout(300)
        # edit sale s1: give it to Jax through the Edit form
        pg.click("button[data-action='edit-sale'][data-id='s1']"); pg.wait_for_timeout(300)
        pg.select_option("#f_who", "Jax"); pg.click("button[data-action='submit-edit-sale']"); pg.wait_for_timeout(400)
        st = pg.evaluate("() => ({b1: window.__t.state().batches.find(b=>b.id==='b1').owner, b2: window.__t.state().batches.find(b=>b.id==='b2').owner, cost1: window.__t.unitCostFor(window.__t.state().sales.find(s=>s.id==='s1')), s1: window.__t.state().sales.find(s=>s.id==='s1').attributedTo})")
        print("after Edit -> Jax: sale owner:", st["s1"], "| its stock entry owner:", st["b1"], "| other sale's stock untouched:", st["b2"], "| cost follows:", st["cost1"])
        # a sale with no payout figure stays blank when saved untouched
        pg.click("button[data-action='edit-sale'][data-id='s2']"); pg.wait_for_timeout(300)
        print("payout box for a sale with no payout:", repr(pg.input_value("#f_profit")))
        pg.click("button[data-action='submit-edit-sale']"); pg.wait_for_timeout(400)
        print("payout after saving untouched:", pg.evaluate("window.__t.state().sales.find(s=>s.id==='s2').netProfit"))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_eo_copy.html").unlink(missing_ok=True)
