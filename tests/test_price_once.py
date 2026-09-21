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
(root / "_v19_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8791", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
SEED = """(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; });
  const p = S.products.find(x => /exeggutor/i.test(x.name)); const ids = S.products.filter(x => /exeggutor/i.test(x.name)).map(x => x.id);
  S.batches = S.batches.filter(b => !ids.includes(b.productId)).concat([
    {id:'e1',productId:p.id,owner:'Jon',quantity:1,unitCost:0,status:'received',createdAt:1,needsReview:true},
    {id:'e2',productId:p.id,owner:'Jon',quantity:1,unitCost:0,status:'received',createdAt:2,needsReview:true},
    {id:'e3',productId:p.id,owner:'Jax',quantity:1,unitCost:0,status:'received',createdAt:3,needsReview:true}]);
  window.__t.render(); }"""
STATE = "() => ['e1','e2','e3'].map(i => { const b = window.__t.state().batches.find(x => x.id === i); return [b.owner, b.unitCost, !!b.costKnown]; })"
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8791/_v19_copy.html#inventory"); pg.wait_for_timeout(1800)
        # A) Add cost once (item strip) -> Jon's 2 and Jax's 1 all priced
        pg.evaluate(SEED, data); pg.wait_for_timeout(200)
        pg.click("button[data-action='open-trip']"); pg.click("button[data-action='trip-toggle-all']"); pg.locator(".trip-row:has-text('Exeggutor') .trip-chk").check(); pg.wait_for_timeout(300)
        print("A scope default:", pg.eval_on_selector("input[name='t_scope']:checked", "e => e.value"))
        pg.select_option("#t_who", "Jon")
        pg.locator(".trip-row:has(.trip-chk:checked) .trip-price").fill("16.45")
        print("A summary:", pg.inner_text("#tripSummary")); pg.click("button[data-action='trip-total-items']"); print("A total now:", pg.input_value("#t_total"))
        pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(300)
        print("A confirm note:", pg.inner_text(".modal-body .hint").replace("\n"," ")[-120:])
        pg.click("button[data-action='trip-apply']"); pg.wait_for_timeout(400)
        print("A after one entry:", pg.evaluate(STATE))
        pg.click(".toast-btn"); pg.wait_for_timeout(300); print("A after undo:", pg.evaluate(STATE))
        # B) Edit one batch, apply to the rest
        pg.evaluate(SEED, data); pg.wait_for_timeout(200)
        pg.locator("button[data-action='edit-batch'][data-id='e1']").click(); pg.wait_for_timeout(300)
        print("B scope options:", [x.replace(chr(10)," ") for x in pg.locator(".modal .seg-choice label").all_inner_texts()])
        pg.fill("#f_cost", "18"); pg.click("button[data-action='submit-edit-batch']"); pg.wait_for_timeout(400)
        print("B after one edit:", pg.evaluate(STATE))
        # A2) trip, only Jon
        pg.evaluate(SEED, data); pg.wait_for_timeout(200)
        pg.click("button[data-action='open-trip']"); pg.click("button[data-action='trip-toggle-all']"); pg.locator(".trip-row:has-text('Exeggutor') .trip-chk").check(); pg.wait_for_timeout(300)
        pg.check("input[name='t_scope'][value='mine']"); print("A2 label:", pg.inner_text("#t_only"))
        pg.locator(".trip-row:has(.trip-chk:checked) .trip-price").fill("10"); pg.click("button[data-action='trip-total-items']")
        pg.click("button[data-action='trip-review']"); pg.click("button[data-action='trip-apply']"); pg.wait_for_timeout(400)
        print("A2 only Jon:", pg.evaluate(STATE))
        # B2) edit, just mine
        pg.evaluate(SEED, data); pg.wait_for_timeout(200)
        pg.locator("button[data-action='edit-batch'][data-id='e1']").click(); pg.wait_for_timeout(300)
        pg.check("input[name='f_scope'][value='mine']"); pg.fill("#f_cost", "12"); pg.click("button[data-action='submit-edit-batch']"); pg.wait_for_timeout(400)
        print("B2 just mine:", pg.evaluate(STATE))
        pg.evaluate(SEED, data); pg.wait_for_timeout(200)
        pg.locator("button[data-action='edit-batch'][data-id='e1']").click(); pg.wait_for_timeout(300)
        pg.check("input[name='f_scope'][value='one']"); pg.fill("#f_cost", "12"); pg.click("button[data-action='submit-edit-batch']"); pg.wait_for_timeout(400)
        print("B3 only this batch:", pg.evaluate(STATE))
        pg.evaluate(SEED, data); pg.wait_for_timeout(200)
        pg.locator("button[data-action='edit-batch'][data-id='e1']").click(); pg.wait_for_timeout(300)
        pg.screenshot(path=str(out / "v21_edit.png"))
        pg.click(".modal button[data-action='close-modal'] >> nth=0"); pg.wait_for_timeout(200)
        pg.evaluate("() => { const b = window.__t.state().batches.find(x=>x.id==='e1'); b.unitCost = 18; b.costKnown = true; }")
        # C) prefill: a new unpriced batch of an item that has a known price
        pg.evaluate("() => { const S = window.__t.state(); S.batches.push({id:'e4',productId:S.batches.find(b=>b.id==='e1').productId,owner:'Jon',quantity:1,unitCost:0,status:'received',createdAt:9}); window.__t.render(); }")
        pg.locator("button[data-action='edit-batch'][data-id='e4']").click(); pg.wait_for_timeout(300)
        print("C edit prefill:", pg.input_value("#f_cost"), "|", pg.inner_text(".modal-body .hint").strip()[:70])
        pg.click(".modal button[data-action='close-modal'] >> nth=0"); pg.wait_for_timeout(200)
        pg.locator(".product-card:has-text('Exeggutor') button[data-action='open-add-batch']").click(); pg.wait_for_timeout(300)
        print("C add prefill:", pg.input_value("#f_cost"))
        print("errors:", errs, "scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_v19_copy.html").unlink(missing_ok=True)
