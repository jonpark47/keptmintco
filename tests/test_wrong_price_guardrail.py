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
(root / "_v25_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8794", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8794/_v25_copy.html#inventory"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        # the mistake: pair price typed as the per-unit price
        pg.click("button[data-action='open-trip']"); pg.click("button[data-action='trip-toggle-all']")
        pg.locator(".trip-row:has-text('Zelda') .trip-chk").check()
        z = pg.locator(".trip-row:has-text('Zelda')"); z.locator(".trip-qty").fill("2"); z.locator(".trip-price").fill("199.98")
        pg.fill("#t_total", "439"); pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(300)
        print("WRONG entry ->", pg.inner_text(".modal-body .trip-out").replace("\n"," | ")[:330])
        pg.click("button[data-action='trip-back']"); pg.wait_for_timeout(200)
        pg.locator(".trip-row:has-text('Zelda') .trip-price").fill("99.99"); pg.fill("#t_total", "219.48"); pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(300)
        print("RIGHT entry ->", pg.inner_text(".modal-body .trip-out").replace("\n"," | ")[:330], "| warn shown:", pg.locator(".warn-line").count())
        pg.click(".modal-head button[data-action='close-modal']")
        # loss pill: make a sale a loss
        pg.evaluate("() => { const S = window.__t.state(); const sa = S.sales.find(x => x.attributedTo==='Jon' && /zelda/i.test((S.products.find(p=>p.id===x.productId)||{}).name)); S.batches.filter(b => b.productId===sa.productId && b.owner==='Jon').forEach(b => { b.unitCost = 219.48; b.costKnown = true; }); window.__t.setTab('sales'); }")
        pg.wait_for_timeout(300)
        print("loss pills on Sales:", pg.locator(".cost-badge.mini:has-text('Loss')").count())
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v25_copy.html").unlink(missing_ok=True)
