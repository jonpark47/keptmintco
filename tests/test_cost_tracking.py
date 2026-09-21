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
(root / "_v15_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8787", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8787/_v15_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        # make a mix: cost one group fully, one partially, one via known zero
        pg.evaluate("""() => { const S = window.__t.state(); const P = S.products;
          const gid = re => P.filter(p => re.test(p.name)).map(p => p.id);
          const zelda = gid(/zelda/i), luc = gid(/lucario/i);
          S.batches.forEach(b => { if (zelda.includes(b.productId)) b.unitCost = 219; });
          S.batches.forEach(b => { if (luc.includes(b.productId)) { b.unitCost = 0; b.costKnown = true; } });
          window.__t.render(); }""")
        pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(400)
        box = pg.locator(".dash-card:has-text('Costs logged')")
        print("cost card:", box.inner_text().replace("\n", " | ")[:260])
        box.screenshot(path=str(out / "v15_costcard.png"))
        pg.click("button[data-action='goto-costs']"); pg.wait_for_timeout(400)
        print("tab:", pg.evaluate("document.body.dataset.tab"), "| filtered cards:", pg.locator(".product-card").count(), "| header:", pg.inner_text(".section-head .count"))
        print("badges:", pg.locator(".cost-badge").all_inner_texts()[:6])
        pg.screenshot(path=str(out / "v15_inv.png"))
        pg.click(".fchip:has-text('All')"); pg.wait_for_timeout(300)
        print("all cards:", pg.locator(".product-card").count(), "| ok badges:", pg.locator(".cost-badge.ok").count(), "| missing badges:", pg.locator(".cost-badge:not(.ok)").count())
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        print("sales chips:", pg.locator(".fchip").all_inner_texts())
        pg.click(".fchip:has-text('Missing cost')"); pg.wait_for_timeout(300); print("missing-cost sales:", pg.locator(".sale-row").count())
        pg.evaluate("window.__t.setTab('settlements')"); pg.wait_for_timeout(300)
        print("tiles:", [t.replace("\n", " | ")[:190] for t in pg.locator(".tile").all_inner_texts()[:3]])
        print("errors:", errs, "scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_v15_copy.html").unlink(missing_ok=True)
