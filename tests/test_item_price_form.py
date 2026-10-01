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
(root / "_v23_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8793", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
SEED = """(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; });
  const ex = S.products.filter(x => /exeggutor/i.test(x.name)); const ids = ex.map(x => x.id);
  S.products.push(Object.assign({}, ex[0], {id:'exB', itemId:'2'}));
  S.batches = S.batches.filter(b => !ids.includes(b.productId)).concat([
    {id:'j1',productId:ex[0].id,owner:'Jon',quantity:2,unitCost:16.15,costKnown:true,status:'received',createdAt:1},
    {id:'x1',productId:'exB',owner:'Jax',quantity:1,unitCost:0,status:'received',createdAt:2,note:'Purchase split you entered — add the unit cost when you have it.',needsReview:true}]);
  window.__t.render(); }"""
ST = "() => ['j1','x1','x2'].map(i => { const b = window.__t.state().batches.find(x => x.id === i); return b ? [b.owner, b.unitCost, !!b.costKnown, b.costMeta ? b.costMeta.price : null] : null; })"
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8793/_v23_copy.html#inventory"); pg.wait_for_timeout(1800)
        pg.evaluate(SEED, data); pg.wait_for_timeout(300)
        card = pg.locator(".product-card:has-text('Exeggutor')")

        # ---- "Add cost" is the one-field everyday screen by default, not the receipt calculator --
        # only Jax has an unpriced batch here, so there's no "who paid this" choice to make either
        card.locator(".cost-strip button").click(); pg.wait_for_timeout(400)
        print("title:", pg.inner_text(".modal-head h3"), "| no tax-calculator fields:", pg.locator(".trip-row").count() == 0)
        print("prefilled from the price already logged elsewhere:", pg.input_value("#qc_cost"), "| no who-paid choice needed:", pg.locator("input[name='qc_scope']").count() == 0)
        pg.screenshot(path=str(out / "v23_quick.png"))

        # ---- change the price and save -- one tap, no tax math
        pg.fill("#qc_cost", "15")
        pg.click("button[data-action='submit-quick-cost']"); pg.wait_for_timeout(400)
        print("after quick save [Jon, Jax]:", pg.evaluate(ST)[:2], "(Jon must stay 16.15, untouched)")
        print("undo toast offered:", pg.locator(".toast-btn").count() > 0)
        pg.click(".toast-btn"); pg.wait_for_timeout(300)
        print("undo restores the unpriced state:", pg.evaluate(ST)[1])

        # ---- re-save for real, then reopen with a second unpriced Jax batch -- still prefilled
        card.locator(".cost-strip button").click(); pg.wait_for_timeout(300)
        pg.click("button[data-action='submit-quick-cost']"); pg.wait_for_timeout(400)
        pg.evaluate("() => { const S = window.__t.state(); S.batches.push({id:'x2',productId:'exB',owner:'Jax',quantity:2,unitCost:0,status:'received',createdAt:9}); window.__t.render(); }")
        card.locator(".cost-strip button").click(); pg.wait_for_timeout(400)
        print("next time prefilled from what was just logged:", pg.input_value("#qc_cost"))

        # ---- the full receipt-total calculator is one tap away, never the first thing shown, and
        # carries over whatever was already typed in the quick field instead of starting blank
        pg.fill("#qc_cost", "15")
        pg.click("button[data-action='open-item-trip-advanced']"); pg.wait_for_timeout(400)
        print("advanced calculator title:", pg.inner_text(".modal-head h3"), "| rows:", pg.locator(".trip-row").count())
        print("carried the quick price over:", pg.input_value(".trip-price"), "| qty label:", pg.locator(".trip-nums label").first.inner_text())
        print("who:", pg.input_value("#t_who"), "| total:", pg.input_value("#t_total"), "| replace ticked:", pg.is_checked("#t_replace"), "| scope:", pg.eval_on_selector("input[name='t_scope']:checked", "e=>e.value"))
        pg.fill(".trip-price", "20"); pg.fill("#t_total", "16.20"); pg.wait_for_timeout(150)
        print("mismatched total vs qty*price warns instead of silently faking a discount:", pg.locator("#tripSummary .hint.warn").count() > 0)
        pg.fill(".trip-price", "15"); pg.fill("#t_total", "33"); pg.wait_for_timeout(150)
        print("a sane total (10% tax) stays quiet:", pg.locator("#tripSummary .hint.warn").count() == 0)
        pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(300)
        print("confirm:", pg.inner_text(".modal-body").replace("\n", " | ")[:330])
        pg.click("button[data-action='trip-apply']"); pg.wait_for_timeout(400)
        print("after advanced apply [Jon, Jax]:", pg.evaluate(ST)[:2], "(Jon must stay 16.15, untouched)")

        # ---- the general multi-item trip (a whole different receipt) is untouched by any of this
        pg.click("button[data-action='open-trip']"); pg.wait_for_timeout(300)
        print("general trip replace default:", pg.is_checked("#t_replace"), "| rows:", pg.locator(".trip-row").count())
        print("errors:", errs, "scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_v23_copy.html").unlink(missing_ok=True)
