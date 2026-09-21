import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_ins_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8814", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (390, 320):
            pg = b.new_page(viewport={"width": w, "height": 844}, has_touch=True, is_mobile=True)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8814/_ins_copy.html#overview"); pg.wait_for_timeout(1500)
            pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); S.sales.forEach((s,i)=>{ if(!s.attributedTo) s.attributedTo = i%2 ? 'Jax':'Jon'; }); window.__t.render(); }", data)
            pg.wait_for_timeout(300)
            print(w, "overview preview:", pg.locator("text=Top earners").count() == 1, "| button:", pg.locator("button[data-action='goto-insights']").count())
            pg.click("button[data-action='goto-insights']"); pg.wait_for_timeout(300)
            print("  title:", pg.inner_text("#pageTitle").strip(), "| hash:", pg.evaluate("location.hash"))
            print("  tiles:", [t.replace("\n", " | ") for t in pg.locator(".tile").all_inner_texts()])
            print("  drops:", [t.replace("\n", " ") for t in pg.locator(".ins-drop").all_inner_texts()])
            print("  items:", pg.locator(".ins-item").count())
            for f in ("roi", "units", "profit"):
                pg.click(f"button[data-action='ins-sort'][data-f='{f}']"); pg.wait_for_timeout(150)
                first = pg.locator(".ins-item .ins-name").first.inner_text()
                print("  sort", f, "-> first:", first[:40], "| chip on:", pg.locator(".fchip.on").inner_text())
            print("  no sideways scroll:", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "| errors:", errs)
            pg.close()
        b.close()
finally:
    srv.terminate(); (root / "_ins_copy.html").unlink(missing_ok=True)
