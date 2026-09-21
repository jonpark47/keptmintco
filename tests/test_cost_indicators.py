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
(root / "_v16_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8788", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8788/_v16_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        for tab in ("overview", "inventory", "preorders", "sales"):
            pg.evaluate(f"window.__t.setTab('{tab}')"); pg.wait_for_timeout(350)
            print(tab, "| cost pills:", pg.locator(".cost-badge").count(), "| strips:", pg.locator(".cost-strip").count())
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        pg.locator(".sale-row").first.screenshot(path=str(out / "v16_sale.png"))
        pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(300)
        pg.locator(".product-card:has(.cost-strip)").first.screenshot(path=str(out / "v16_inv.png"))
        pg.locator(".cost-strip button").first.click(); pg.wait_for_timeout(400)
        print("modal:", pg.inner_text(".modal-head h3"))
        print("errors:", errs, "scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_v16_copy.html").unlink(missing_ok=True)
