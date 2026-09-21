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
(root / "_r.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8805", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8805/_r.html#sales"); pg.wait_for_timeout(1500)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        n0 = pg.evaluate("window.__t.state().sales.length")
        pg.locator("button[data-action='open-add-sale']").first.click(); pg.wait_for_timeout(300)
        ids = pg.evaluate("Array.from(document.querySelectorAll('.modal input, .modal select, .modal textarea')).map(e => e.id + ':' + e.type)")
        print("add-sale fields:", ids)
        pg.fill("#f_profit", "42.5")
        pg.click("button[data-action='submit-add-sale']"); pg.wait_for_timeout(500)
        n1 = pg.evaluate("window.__t.state().sales.length")
        print("sales before/after:", n0, n1, "| toast:", pg.inner_text("#toastRoot").replace("\n", " ")[:80])
        pg.locator("button[data-action='edit-sale']").first.click(); pg.wait_for_timeout(300)
        pg.fill("#f_profit", "50"); pg.click("button[data-action='submit-edit-sale']"); pg.wait_for_timeout(400)
        print("edit ok, toast:", pg.inner_text("#toastRoot").replace("\n", " ")[-60:])
        print("import bar present:", pg.locator(".import-bar, #dropzone").count(), "| errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_r.html").unlink(missing_ok=True)
