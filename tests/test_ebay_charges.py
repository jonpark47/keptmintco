import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_ch_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8813", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (390, 320):
            pg = b.new_page(viewport={"width": w, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8813/_ch_copy.html#overview"); pg.wait_for_timeout(1500)
            pg.evaluate("""() => { const S = window.__t.state();
              S.products=[{id:'p1',name:'Test Item'}];
              S.sales=[{id:'s1',productId:'p1',attributedTo:'Jon',quantitySold:1,netProfit:80,saleDate:'2026-09-01',createdAt:1,lifecycleStatus:'pending'}];
              S.batches=[]; S.settlements=[]; S.expenses=[]; window.__t.render(); }""")
            print(w, "px, no charges -> card hidden:", pg.locator("text=eBay charges").count() == 0)
            pg.evaluate("""() => { const S = window.__t.state(); const d = new Date(); const t = d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-05';
              S.expenses=[{id:'e1',kind:'NON_SALE_CHARGE',feeType:'AD_FEE',amount:-4.25,date:t,createdAt:1},
                          {id:'e2',kind:'CREDIT',feeType:'',amount:1.1,date:t,memo:'ad fee credit with a very long explanation that must wrap instead of pushing the page sideways',createdAt:2},
                          {id:'e3',kind:'NON_SALE_CHARGE',feeType:'SUBSCRIPTION_FEE',amount:-4.95,date:'2026-01-02',createdAt:0}]; window.__t.render(); }""")
            pg.wait_for_timeout(200)
            print(w, "px, card:", pg.inner_text(".section-head:has-text('eBay charges')").replace("\n", " | "))
            print("  rows:", [re.sub(r"[A-Z][a-z]{2} \d+, \d{4}", "DATE", r.replace("\n", " ")) for r in pg.locator(".confirm-row").all_inner_texts()])
            print("  no sideways scroll:", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
            print("  errors:", errs)
            pg.close()
        b.close()
finally:
    srv.terminate(); (root / "_ch_copy.html").unlink(missing_ok=True)
