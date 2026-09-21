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
(root / "_v18_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8790", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8790/_v18_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        miss = pg.evaluate("window.__t.state().products.length")
        for tab in ("overview", "sales", "settlements", "inventory"):
            pg.evaluate(f"window.__t.setTab('{tab}')"); pg.wait_for_timeout(300)
            print(tab, "| review banner:", pg.inner_text("#reviewBanner").replace("\n"," ")[:80] if pg.locator("#reviewBanner .banner").count() else "-")
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        pg.click("#reviewBanner button[data-action='goto-costs']"); pg.wait_for_timeout(400)
        print("after click -> tab:", pg.evaluate("document.body.dataset.tab"), "| header:", pg.inner_text(".section-head .count"), "| cards:", pg.locator(".product-card").count(), "| all show strip:", pg.locator(".product-card").count() == pg.locator(".product-card .cost-strip").count(), "| chip on:", pg.locator(".fchip.on").inner_text().replace("\n"," "))
        pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(300)
        pg.click("#costBanner button[data-action='goto-costs']"); pg.wait_for_timeout(400)
        print("panel 'See all' -> tab:", pg.evaluate("document.body.dataset.tab"), "| cards:", pg.locator(".product-card").count())
        pg.click(".bottom-tabbar .navbtn[data-tab='overview']"); pg.wait_for_timeout(200)
        pg.click(".bottom-tabbar .navbtn[data-tab='inventory']"); pg.wait_for_timeout(300)
        print("normal Inventory tap shows everything:", pg.locator(".product-card").count())
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v18_copy.html").unlink(missing_ok=True)
