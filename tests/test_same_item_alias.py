import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render,unitCostFor:unitCostFor,groups:function(){return productGroupList().map(function(g){return [g.p.name,g.pids.length];});}}; boot();", 1)
(root / "_al_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8815", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8815/_al_copy.html#inventory"); pg.wait_for_timeout(1500)
        def setup(same_as, bundle=False):
            return pg.evaluate("""(a) => { const S = window.__t.state();
              S.products=[{id:'A',name:'Pokemon Ascended Heroes Elite Trainer Box',createdAt:1},
                          {id:'B',name:'NEW Pokemon Ascended Heroes Elite Trainer Box SEALED',createdAt:2}].concat(a.bundle ? [{id:'C',name:'Pokemon Ascended Heroes Booster Bundle',createdAt:3}] : []);
              if (a.same) S.products[1].sameAs = a.same;
              S.batches=[{id:'b1',productId:'A',owner:'Jon',quantity:2,unitCost:50,costKnown:true,status:'received',createdAt:1}];
              S.sales=[{id:'s1',productId:'A',attributedTo:'Jon',quantitySold:1,netProfit:100,saleDate:'2026-09-01',createdAt:1,lifecycleStatus:'pending'},
                       {id:'s2',productId:'B',attributedTo:'Jon',quantitySold:1,netProfit:100,saleDate:'2026-09-08',createdAt:2,lifecycleStatus:'pending'}];
              if (a.bundle) S.sales.push({id:'s3',productId:'C',attributedTo:'Jon',quantitySold:1,netProfit:60,saleDate:'2026-09-09',createdAt:3,lifecycleStatus:'pending'});
              S.settlements=[]; S.cancelled=[]; S.expenses=[]; window.__t.render();
              return {groups: window.__t.groups(), costs: S.sales.map(s => window.__t.unitCostFor(s))}; }""", {"same": same_as, "bundle": bundle})
        r = setup(None)
        print("edited title, not confirmed -> kept apart:", r["groups"], "| sale on the relist has no cost yet:", r["costs"])
        r = setup("A")
        print("confirmed same item -> one group:", r["groups"], "| both sales share the stock and cost:", r["costs"])
        r = setup("A", bundle=True)
        print("a different product (bundle) is never merged:", r["groups"])
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_al_copy.html").unlink(missing_ok=True)
