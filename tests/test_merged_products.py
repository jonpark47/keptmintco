import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_m_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8779", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8779/_m_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        n_raw = len(data["products"])
        pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(400)
        cards = pg.locator(".product-card").count()
        print("products raw:", n_raw, "cards shown:", cards, "| header:", pg.inner_text(".section-head .count"))
        for t in ("Lucario", "Exeggutor"):
            print(t, "cards:", pg.locator(f".product-card:has-text('{t}')").count())
        # seed 2 Jon / 1 Jax for Lucario group with costs, check split line + profit
        pg.evaluate("""() => { const S = window.__t.state(); const ps = S.products.filter(p => /lucario/i.test(p.name));
            S.batches = S.batches.concat([{id:'t1',productId:ps[0].id,owner:'Jon',quantity:2,unitCost:20,status:'received',createdAt:1},{id:'t2',productId:ps[1].id,owner:'Jax',quantity:1,unitCost:15,status:'received',createdAt:2}]);
            S.sales.filter(s => ps.some(p => p.id===s.productId)).forEach((s,i)=>{ s.attributedTo = i===0?'Jon':'Jax'; }); window.__t.render(); }""")
        print("split line:", pg.inner_text(".product-card:has-text('Lucario') .split-line").replace("\n"," "))
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(400)
        print("sale money:", [x.replace("\n"," | ") for x in pg.locator(".sale-money").all_inner_texts()[:4]])
        pg.evaluate("window.__t.setTab('settlements')"); pg.wait_for_timeout(400)
        print("tiles:", [x.replace("\n"," | ")[:110] for x in pg.locator(".tile").all_inner_texts()[:2]])
        pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(300)
        pg.screenshot(path=str(out / "m_inv.png"), clip={"x":0,"y":0,"width":390,"height":700})
        print("scrollW", pg.evaluate("document.documentElement.scrollWidth"), "errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_m_copy.html").unlink(missing_ok=True)
