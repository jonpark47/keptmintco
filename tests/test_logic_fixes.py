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
(root / "_v28.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8807", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
fails = []
def check(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label + (" | " + str(extra) if extra else ""))
    if not cond: fails.append(label)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8807/_v28.html#overview"); pg.wait_for_timeout(1500)
        d = json.loads(json.dumps(data))
        # one sale unassigned, one cancelled, one orphan product with no sale/batch
        first = d["sales"][0]; first["attributedTo"] = None; first["needsOwner"] = True; first["ownerSource"] = "auto"
        canc = json.loads(json.dumps(d["sales"][1])); canc["id"] = "cancelled1"; canc["orderState"] = "cancelled"; canc["netProfit"] = 999.0; canc["attributedTo"] = "Jon"
        d["products"].append({"id": "orphan", "name": "ORPHAN PRODUCT NOBODY BOUGHT", "createdAt": 1})
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", d)
        base_total = pg.evaluate("window.__t.state().sales.reduce((a,s)=>a+Number(s.netProfit||0),0)")
        pg.evaluate("(c) => { const S = window.__t.state(); S.cancelled = [c]; window.__t.render(); }", canc)
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(400)
        tiles = pg.locator(".tiles.mini .tile .value").all_inner_texts()
        check("cancelled: $999 sale is NOT in the total payout", tiles[0].replace(",", "") == "${:.2f}".format(base_total), tiles)
        check("cancelled: hidden from the All list", pg.locator(".sale-row.cancelled").count() == 0)
        chips = pg.locator(".fchip").all_inner_texts()
        check("cancelled: chip shows 1", any(c.replace("\n", "").startswith("Cancelled") and c.strip().endswith("1") for c in chips), chips)
        pg.click(".fchip:has-text('Cancelled')"); pg.wait_for_timeout(300)
        check("cancelled: chip lists it faded with a Remove button", pg.locator(".sale-row.cancelled").count() == 1 and pg.locator(".sale-row.cancelled button[data-action='delete-sale']").count() == 1)
        check("cancelled: no owner/edit controls on it", pg.locator(".sale-row.cancelled button[data-action='edit-sale']").count() == 0)
        pg.click(".fchip:has-text('All')"); pg.wait_for_timeout(200)
        # orphan product hidden from Inventory
        pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(300)
        check("inventory: product with no sales or batches is hidden", "ORPHAN" not in pg.inner_text("#main"))
        # edit an unassigned sale: stays unassigned unless you pick
        sid = first["id"]
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        pg.click(".fchip:has-text('Unassigned')"); pg.wait_for_timeout(200)
        pg.locator(f"button[data-action='edit-sale'][data-id='{sid}']").click(); pg.wait_for_timeout(300)
        opts = pg.evaluate("Array.from(document.querySelectorAll('#f_who option')).map(o => o.textContent)")
        check("edit sale: unassigned sale shows an Unassigned option first", opts[0] == "Unassigned" and pg.input_value("#f_who") == "", opts)
        pg.fill("#f_note", "just a note"); pg.click("button[data-action='submit-edit-sale']"); pg.wait_for_timeout(400)
        sale = pg.evaluate("(id) => window.__t.state().sales.find(s => s.id === id)", sid)
        check("edit sale: saving a note does NOT silently assign Jon", sale["attributedTo"] in (None,) and not sale.get("ownerSource") == "manual", (sale["attributedTo"], sale.get("ownerSource")))
        pg.locator(f"button[data-action='edit-sale'][data-id='{sid}']").click(); pg.wait_for_timeout(300)
        pg.select_option("#f_who", "Jax"); pg.fill("#f_profit", "77.77"); pg.keyboard.press("Enter"); pg.wait_for_timeout(500)
        sale = pg.evaluate("(id) => window.__t.state().sales.find(s => s.id === id)", sid)
        check("edit sale: Enter key saves", sale["attributedTo"] == "Jax", sale["attributedTo"])
        check("edit sale: owner and payout you typed are locked as manual", sale.get("ownerSource") == "manual" and sale.get("profitSource") == "manual" and sale.get("needsOwner") is False, (sale.get("ownerSource"), sale.get("profitSource")))
        # remove a sale takes its placeholder batch with it
        pg.evaluate("""(id) => { const S = window.__t.state(); S.batches.push({id:'ph1', productId: S.sales.find(s=>s.id===id).productId, owner:'Jax', quantity:1, unitCost:0, sourceSaleId:id, note:'Auto-added to cover a sale — not yet received from the supplier. Cost unknown; edit with the real purchase cost once you know it.'}); window.__t.render(); }""", sid)
        n_b = pg.evaluate("window.__t.state().batches.length")
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        pg.click(".fchip:has-text('All')"); pg.wait_for_timeout(200)
        pg.locator(f"button[data-action='delete-sale'][data-id='{sid}']").click(); pg.wait_for_timeout(300)
        check("remove: confirm explains eBay sales stay removed", "stays removed" in pg.inner_text(".modal-body") or "auto-created" in pg.inner_text(".modal-body"), pg.inner_text(".modal-body")[:120])
        pg.click("button[data-action='confirm-yes']"); pg.wait_for_timeout(400)
        st = pg.evaluate("({sales: window.__t.state().sales.some(s=>s.id==='%s'), batch: window.__t.state().batches.some(b=>b.id==='ph1')})" % sid)
        check("remove: sale gone AND its unpriced placeholder batch gone", st["sales"] is False and st["batch"] is False, st)
        # settlement prefill + inputmode
        pg.evaluate("""() => { const S = window.__t.state(); S.settlements = []; S.sales.forEach(s => { s.attributedTo = 'Jon'; s.lifecycleStatus = 'completed'; }); window.__t.render(); }""")
        owed = pg.evaluate("window.__t.state().sales.reduce((a,s)=>a+Number(s.netProfit||0),0)")
        pg.evaluate("window.__t.setTab('settlements')"); pg.wait_for_timeout(300)
        pg.locator("button[data-action='open-add-settlement']").first.click(); pg.wait_for_timeout(300)
        check("settlement: form starts as Jax -> Jon for what is owed", pg.input_value("#f_from") == "Jax" and pg.input_value("#f_to") == "Jon" and abs(float(pg.input_value("#f_amount")) - round(owed, 2)) < 0.011, (pg.input_value("#f_from"), pg.input_value("#f_amount"), owed))
        check("modal: money field asks for the decimal keypad", pg.get_attribute("#f_amount", "inputmode") == "decimal")
        pg.fill("#f_amount", "0"); pg.click("button[data-action='submit-add-settlement']"); pg.wait_for_timeout(300)
        check("settlement: zero amount refused", pg.locator(".modal").count() == 1)
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v28.html").unlink(missing_ok=True)
print("RESULT:", "ALL PASSED" if not fails else "FAILED: " + ", ".join(fails))
