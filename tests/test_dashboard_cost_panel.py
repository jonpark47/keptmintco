import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
for s in data["sales"]:
    if s.get("createdBy") == "ebay-sync" and s.get("ownerSource") == "auto":
        s["attributedTo"] = "Jon"; s["needsOwner"] = False   # answered, so the cost panel is what leads
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_v17_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8789", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, vp, mob in (("m", {"width": 390, "height": 844}, True), ("d", {"width": 1280, "height": 900}, False)):
            ctx = b.new_context(viewport=vp, has_touch=mob, is_mobile=mob); pg = ctx.new_page()
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8789/_v17_copy.html"); pg.wait_for_timeout(1800)
            pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
            pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(500)
            print(name, "panel:", pg.inner_text("#costBanner").replace("\n", " | ")[:230])
            print(name, "nav dots:", pg.locator(".nav-dot").all_inner_texts())
            pg.screenshot(path=str(out / f"v17_{name}.png"))
            if name == "m":
                pg.click("#costBanner button[data-action='cost-all']"); pg.wait_for_timeout(400)
                print("Add all -> ticked:", pg.locator(".trip-chk:checked").count(), "of", pg.locator(".trip-chk").count())
                pg.click(".modal-head button[data-action='close-modal']")
                pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
                print("on Sales tab, panel hidden:", pg.locator("#costBanner .owner-queue").count() == 0, "| nav dot still:", pg.locator(".nav-dot").count() > 0)
            print(name, "errors:", errs, "scrollW", pg.evaluate("document.documentElement.scrollWidth"))
            ctx.close()
        b.close()
finally:
    srv.terminate(); (root / "_v17_copy.html").unlink(missing_ok=True)
