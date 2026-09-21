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
(root / "_v14_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8786", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, color_scheme=scheme); pg = ctx.new_page()
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8786/_v14_copy.html#inventory"); pg.wait_for_timeout(1800)
            pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
            pg.click("button[data-action='open-trip']"); pg.wait_for_timeout(300)
            pg.click("button[data-action='trip-toggle-all']")
            rows = pg.locator(".trip-row")
            rows.nth(0).locator(".trip-chk").check(); rows.nth(0).locator(".trip-qty").fill("1"); rows.nth(0).locator(".trip-price").fill("50")
            rows.nth(1).locator(".trip-chk").check(); rows.nth(1).locator(".trip-qty").fill("1"); rows.nth(1).locator(".trip-price").fill("50")
            rows.nth(2).locator(".trip-chk").check()  # left blank on purpose to show the flag
            pg.select_option("#t_who", "Jon"); pg.fill("#t_total", "162")
            if scheme == "light":
                print("no 'other' yet:", pg.inner_text("#tripSummary"))
                pg.fill("#t_other", "50"); pg.fill("#t_otherqty", "1"); pg.wait_for_timeout(150)
                print("with other $50:", pg.inner_text("#tripSummary"))
            else:
                pg.fill("#t_other", "50")
            pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(500)
            pg.screenshot(path=str(out / f"v14_flag_{scheme}.png"))
            if scheme == "light":
                pg.click("button[data-action='trip-skip-all']"); pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(300)
                print("confirm:", pg.inner_text(".modal-body").replace("\n", " | ")[:300])
            print(scheme, "errors:", errs)
            ctx.close()
        b.close()
finally:
    srv.terminate(); (root / "_v14_copy.html").unlink(missing_ok=True)
