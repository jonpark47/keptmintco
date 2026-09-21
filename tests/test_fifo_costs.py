import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},render:render,unitCostFor:unitCostFor,saleProfit:saleProfit}; boot();", 1)
(root / "_fifo_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8811", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8811/_fifo_copy.html"); pg.wait_for_timeout(1500)
        def scenario(batches, sales):
            return pg.evaluate("""(d) => { const S = window.__t.state();
              S.products = [{id:'p1', name:'Ascended Heroes Elite Trainer Box'}];
              S.batches = d.b.map((x,i)=>Object.assign({id:'b'+i, productId:'p1', owner:'Jon', status:'received', costKnown:true}, x));
              S.sales = d.s.map((x,i)=>Object.assign({id:'s'+i, productId:'p1', attributedTo:'Jon', quantitySold:1, netProfit:80, saleDate:'2026-09-0'+(i+1), createdAt:i}, x));
              S.cancelled = []; S.settlements = [];
              return S.sales.map(s => window.__t.unitCostFor(s)); }""", {"b": batches, "s": sales})
        wk5 = {"unitCost": 50, "quantity": 2, "createdAt": 1}
        wk8 = {"unitCost": 55, "quantity": 2, "createdAt": 2}
        print("week 5 only, 2 sales:", scenario([wk5], [{}, {}]))
        print("then week 8 bought (old sales must not move):", scenario([wk5, wk8], [{}, {}]))
        print("third sale lands on week 8:", scenario([wk5, wk8], [{}, {}, {}]))
        print("one sale of 3 units spans both lots:", scenario([wk5, wk8], [{"quantitySold": 3}]))
        print("week 8 lot not priced yet:", scenario([wk5, {"quantity": 2, "createdAt": 2, "costKnown": False, "unitCost": 0}], [{}, {}, {}]))
        print("other owner's purchase is not used:", scenario([wk5], [{"attributedTo": "Jax"}]))
        print("no owner yet:", scenario([wk5], [{"attributedTo": None}]))
        print("more sold than bought:", scenario([wk5], [{}, {}, {}]))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate()
