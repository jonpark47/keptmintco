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
(root / "_v12_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8785", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8785/_v12_copy.html#inventory"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        pg.click("button[data-action='open-trip']"); pg.wait_for_timeout(300)
        n = pg.locator(".trip-row").count(); on = pg.locator(".trip-chk:checked").count()
        print("rows:", n, "ticked by default:", on)
        # fill price on first two rows only, leave the rest blank
        rows = pg.locator(".trip-row")
        rows.nth(0).locator(".trip-price").fill("20"); rows.nth(1).locator(".trip-price").fill("10")
        pg.fill("#t_total", "35"); pg.select_option("#t_who", "Jon")
        pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(500)
        print("flagged rows:", pg.locator(".trip-row.missing").count(), "| still on form:", pg.locator("#t_total").count() == 1, "| toast:", pg.inner_text("#toastRoot").replace("\n"," ")[:90])
        pg.screenshot(path=str(out / "v12_flag.png"))
        # first flagged: $0 ; second flagged: skip ; rest: skip via clear all then retick two
        print('bar:', pg.inner_text('#tripBlankBar').replace(chr(10),' | '))
        flagged = pg.locator(".trip-row.missing")
        flagged.nth(0).locator("button[data-action='trip-zero']").click()
        print("after $0 -> flagged:", pg.locator(".trip-row.missing").count(), "| price value set:", rows.nth(2).locator(".trip-price").input_value() if False else "")
        pg.click('button[data-action="trip-skip-all"]'); print('bar gone:', pg.locator('#tripBlankBar').count() == 0)
        print("all resolved; ticked now:", pg.locator(".trip-chk:checked").count(), "| summary:", pg.inner_text("#tripSummary"))
        pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(400)
        print("confirm rows:", pg.locator(".modal .trip-out").count(), "|", pg.inner_text(".modal-body").replace("\n"," | ")[:330])
        pg.screenshot(path=str(out / "v12_confirm.png"))
        pg.click("button[data-action='trip-apply']"); pg.wait_for_timeout(500)
        res = pg.evaluate("() => window.__t.state().batches.filter(b => b.costKnown).map(b => [b.owner, b.quantity, b.unitCost, b.costKnown])")
        print("costKnown batches:", res)
        pg.click(".toast-btn"); pg.wait_for_timeout(300)
        print("after undo known:", pg.evaluate("window.__t.state().batches.filter(b=>b.costKnown).length"))
        # zero cost counts as known for profit
        pg.evaluate("""() => { const S = window.__t.state(); S.sales.forEach(sa => { sa.attributedTo = 'Jon'; });
            S.batches = S.batches.filter(b => !S.sales.some(sa => sa.productId === b.productId)).concat(S.sales.map((sa,i) => ({id:'z'+i, productId: sa.productId, owner:'Jon', quantity:1, unitCost:0, costKnown:true, status:'received', createdAt:1}))); window.__t.render(); }""")
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        print("first sale money:", pg.locator(".sale-money").first.inner_text().replace("\n"," | "))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v12_copy.html").unlink(missing_ok=True)
