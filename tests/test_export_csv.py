import re, subprocess, time, pathlib, sys, json, csv, io
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_v29.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8808", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, accept_downloads=True); pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8808/_v29.html#sales"); pg.wait_for_timeout(1500)
        d = json.loads(json.dumps(data)); d["sales"][0]["buyerName"] = 'weird, "quoted" buyer'
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); S.cancelled = [Object.assign({}, S.sales[1], {id:'cx', orderState:'cancelled'})]; window.__t.render(); }", d)
        with pg.expect_download() as dl:
            pg.click("button[data-action='export-sales']")
        path = dl.value.path(); text = open(path, encoding="utf-8-sig").read()
        rows = list(csv.reader(io.StringIO(text)))
        print("file:", dl.value.suggested_filename, "| rows:", len(rows) - 1, "| header:", rows[0][:6])
        print("quoted buyer survived:", any('weird, "quoted" buyer' in r for r in rows))
        print("cancelled row marked:", any(r[-1] == "Cancelled or refunded" for r in rows), "| profit blank for it:", [r[9] for r in rows if r[-1] == "Cancelled or refunded"])
        print("first data row:", rows[1])
        print("eBay links on cards:", pg.locator(".sale-row a[href*='ebay.com/sh/ord/details']").count(), "| errors:", errs, "| scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_v29.html").unlink(missing_ok=True)
