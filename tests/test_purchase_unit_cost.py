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
(root / "_v10_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8783", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8783/_v10_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        luc = lambda: pg.evaluate("() => { const S = window.__t.state(); const ids = S.products.filter(p=>/lucario/i.test(p.name)).map(p=>p.id); return S.batches.filter(b=>ids.includes(b.productId) && (b.note===''||b.note.startsWith('Purchase split'))).map(b=>[b.owner,b.quantity,b.unitCost,b.needsReview,b.note.slice(0,8)]); }")
        pg.click("#ownerBanner .owner-queue-row:has-text('Lucario') >> text=Both, split evenly"); pg.wait_for_timeout(300)
        print("cost field present:", pg.locator("#p_cost").count())
        pg.fill("#p_cost", "24.5"); pg.click(".modal button[data-action='bought-split']"); pg.wait_for_timeout(300)
        pg.click(".modal button[data-action='submit-bought']"); pg.wait_for_timeout(300)
        print("cost kept after Back+Review:", pg.input_value("#p_cost"))
        pg.screenshot(path=str(out / "v10_confirm.png"))
        pg.click("button[data-action='confirm-purchase']"); pg.wait_for_timeout(500)
        print("batches with cost:", luc(), "|", pg.inner_text("#toastRoot").replace("\n"," "))
        pg.click(".toast-btn"); pg.wait_for_timeout(400); print("after undo:", luc())
        pg.click("#ownerBanner .owner-queue-row:has-text('Lucario') >> text=Jon bought all"); pg.wait_for_timeout(300)
        pg.click("button[data-action='confirm-purchase']"); pg.wait_for_timeout(500)
        print("no cost typed:", luc(), "|", pg.inner_text("#toastRoot").replace("\n"," "))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v10_copy.html").unlink(missing_ok=True)
