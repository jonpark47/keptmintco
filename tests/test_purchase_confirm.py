import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
for s in data["sales"]:
    if s.get("createdBy") == "ebay-sync" and s.get("ownerSource") == "auto":
        s["attributedTo"] = None; s["needsOwner"] = True
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_c_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8776", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8776/_c_copy.html"); pg.wait_for_timeout(2200)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(500)
        def owners(w):
            return pg.evaluate("(w) => { const S = window.__t.state(); return S.sales.filter(s => (S.products.find(p => p.id === s.productId)||{}).name.toLowerCase().includes(w)).map(s => [s.buyerName, s.netProfit, s.attributedTo]); }", w)
        nb = lambda: pg.evaluate("window.__t.state().batches.length")
        n0 = nb()
        pg.click("#ownerBanner .owner-queue-row:has-text('Lucario') >> text=Both, split evenly"); pg.wait_for_timeout(500)
        print("confirm modal text:", pg.inner_text(".modal, #modalRoot").replace("\n", " | ")[:400])
        print("after tap: batches changed?", nb() != n0, "| owners:", owners("lucario"))
        pg.screenshot(path=str(out / "c_confirm.png"))
        # Back -> custom form keeps values
        pg.click("text=Back"); pg.wait_for_timeout(300)
        print("custom values:", pg.input_value("#f_bj"), pg.input_value("#f_bx"))
        pg.fill("#f_bj", "1"); pg.fill("#f_bx", "2")
        pg.click("button[data-action='submit-bought']"); pg.wait_for_timeout(300)
        print("confirm 1/2:", pg.inner_text(".confirm-counts").replace("\n", " "))
        pg.click("button[data-action='confirm-purchase']"); pg.wait_for_timeout(600)
        print("after confirm owners:", owners("lucario"), "batches added:", nb() - n0)
        print("toast:", pg.inner_text("#toastRoot").replace("\n", " "))
        pg.click(".toast-btn"); pg.wait_for_timeout(600)
        print("after undo owners:", owners("lucario"), "batches delta:", nb() - n0)
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_c_copy.html").unlink(missing_ok=True)
