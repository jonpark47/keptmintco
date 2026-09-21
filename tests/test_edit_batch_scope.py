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
(root / "_v9b_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8782", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8782/_v9b_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("""(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; });
          const p = S.products[0]; S.batches = S.batches.concat([{id:'a1',productId:p.id,owner:'Jon',quantity:1,unitCost:0,status:'received',createdAt:1,needsReview:true},{id:'a2',productId:p.id,owner:'Jon',quantity:2,unitCost:0,status:'received',createdAt:2,note:'Purchase split you entered — add the unit cost when you have it.'}]); window.__t.render(); }""", data)
        pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(300)
        pg.locator("button[data-action='edit-batch'][data-id='a1']").click(); pg.wait_for_timeout(300)
        print("scope options:", pg.locator(".modal .seg-choice label").count())
        pg.fill("#f_cost", "12.34"); pg.click("button[data-action='submit-edit-batch']"); pg.wait_for_timeout(400)
        print("costs:", pg.evaluate("['a1','a2'].map(i => { const b = window.__t.state().batches.find(x=>x.id===i); return [b.unitCost, b.note||'', b.needsReview]; })"), "|", pg.inner_text("#toastRoot").replace("\n"," "))
        pg.click("button[data-action='open-trip']"); pg.wait_for_timeout(300)
        pg.locator(".trip-row").first.locator(".trip-chk").check()
        pg.screenshot(path=str(out / "v9b_trip.png"))
        pg.click("button[data-action='close-modal'] >> text=Cancel")
        pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(400)
        box = pg.locator(".dash-grid").bounding_box()
        pg.screenshot(path=str(out / "v9b_dash.png"), full_page=True, clip={"x":0,"y":box["y"]+pg.evaluate("window.scrollY")-10,"width":390,"height":min(box["height"]+20,820)})
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v9b_copy.html").unlink(missing_ok=True)
