import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_or_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8821", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8821/_or_copy.html#inventory"); pg.wait_for_timeout(1500)
        pg.evaluate("""() => { const S = window.__t.state();
          S.products=[{id:'a',name:'Zoro Sanji Club Card (old single listing, order cancelled)'},
                      {id:'b',name:'Nami Robin Club Card (old single listing, order cancelled)'},
                      {id:'c',name:'3x Zoro Sanji Nami Robin bundle (new listing, sold)'},
                      {id:'d',name:'Bought in store, not sold yet'},
                      {id:'e',name:'Relisted after a cancel, still sold once'}];
          S.batches=[{id:'b1',productId:'a',owner:'Jon',quantity:2,unitCost:30,costKnown:true,status:'received',createdAt:1},
                     {id:'b2',productId:'b',owner:'Jon',quantity:1,unitCost:40,costKnown:true,status:'received',createdAt:2},
                     {id:'b3',productId:'c',owner:'Jon',quantity:1,unitCost:0,costKnown:false,status:'received',createdAt:3},
                     {id:'b4',productId:'d',owner:'Jon',quantity:3,unitCost:10,costKnown:true,status:'received',createdAt:4},
                     {id:'b5',productId:'e',owner:'Jon',quantity:1,unitCost:5,costKnown:true,status:'received',createdAt:5}];
          S.sales=[{id:'s3',productId:'c',attributedTo:'Jon',quantitySold:1,netProfit:200,saleDate:'2026-09-21',createdAt:3,lifecycleStatus:'pending'},
                   {id:'s5',productId:'e',attributedTo:'Jon',quantitySold:1,netProfit:20,saleDate:'2026-09-20',createdAt:5,lifecycleStatus:'pending'}];
          S.cancelled=[{id:'s1',productId:'a',attributedTo:'Jon',quantitySold:2,netProfit:100,saleDate:'2026-09-19',createdAt:1,orderState:'cancelled'},
                       {id:'s2',productId:'b',attributedTo:'Jon',quantitySold:1,netProfit:60,saleDate:'2026-09-19',createdAt:2,orderState:'cancelled'},
                       {id:'s5x',productId:'e',attributedTo:'Jon',quantitySold:1,netProfit:20,saleDate:'2026-09-18',createdAt:1,orderState:'cancelled'}];
          S.settlements=[]; S.expenses=[]; window.__t.render(); }""")
        pg.wait_for_timeout(300)
        names = [n.replace("\n", " ") for n in pg.locator(".product-card h3").all_inner_texts()]
        print("nav tabs:", [t.strip() for t in pg.locator(".bottom-tabbar .navbtn").all_inner_texts()], "| page title:", pg.inner_text("#pageTitle").strip())
        print("items listed:", sorted(names))
        print("old cancelled single listings hidden:", not any("old single listing" in n for n in names))
        print("bought-in-store item still shown:", any("Bought in store" in n for n in names), "| relisted-and-still-sold shown:", any("Relisted after" in n for n in names), "| new bundle shown:", any("3x Zoro" in n for n in names))
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_or_copy.html").unlink(missing_ok=True)
