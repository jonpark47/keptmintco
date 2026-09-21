import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},render:render,allocateSales:allocateSales}; boot();", 1)
(root / "_al2_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8823", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8824/_al2_copy.html".replace("8824", "8823")); pg.wait_for_timeout(1500)
        def alloc(sales, units):
            return pg.evaluate("([s,u]) => { const r = window.__t.allocateSales(s.map(x => Object.assign({ownerSource:'auto', lifecycleStatus:'pending'}, x)), u); return s.map(x => r[x.id] === undefined ? 'kept' : r[x.id]); }", [sales, units])
        four = [{"id": "a", "netProfit": 90, "quantitySold": 1}, {"id": "b", "netProfit": 80, "quantitySold": 1}, {"id": "c", "netProfit": 70, "quantitySold": 1}, {"id": "d", "netProfit": 60, "quantitySold": 1}]
        print("Jon bought 3, Jax 0, four sales:", alloc(four, {"Jon": 3, "Jax": 0}))
        print("Jon 2, Jax 2, four sales:", alloc(four, {"Jon": 2, "Jax": 2}))
        print("Jon 0, Jax 2, four sales:", alloc(four, {"Jon": 0, "Jax": 2}))
        print("Jon 1, Jax 1, a 2-unit order:", alloc([{"id": "x", "netProfit": 100, "quantitySold": 2}], {"Jon": 1, "Jax": 1}))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_al2_copy.html").unlink(missing_ok=True)
