import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
for s in data["sales"]:
    if s.get("createdBy") == "ebay-sync" and s.get("ownerSource") == "auto":
        s["attributedTo"] = None; s["needsOwner"] = True
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_v9_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8781", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8781/_v9_copy.html"); pg.wait_for_timeout(1800)
        pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
        unassigned = lambda: pg.evaluate("window.__t.state().sales.filter(s=>!s.attributedTo).length")
        u0 = unassigned(); print("unassigned at start:", u0)
        # single sale: tap -> modal, nothing written
        pg.click("#ownerBanner button[data-action='assign-owner'][data-who='Jon'] >> nth=0"); pg.wait_for_timeout(300)
        print("modal title:", pg.inner_text(".modal-head h3"), "| still unassigned:", unassigned() == u0)
        pg.screenshot(path=str(out / "v9_confirm_owner.png"))
        pg.click("button[data-action='close-modal'] >> text=Cancel"); pg.wait_for_timeout(200)
        print("after cancel unassigned:", unassigned() == u0)
        pg.click("#ownerBanner button[data-action='assign-owner'][data-who='Jon'] >> nth=0"); pg.click("button[data-action='confirm-owner']"); pg.wait_for_timeout(500)
        print("after confirm unassigned:", unassigned(), "| toast:", pg.inner_text("#toastRoot").replace("\n"," "))
        pg.click(".toast-btn"); pg.wait_for_timeout(500)
        print("after undo unassigned:", unassigned())
        pg.click("#ownerBanner button[data-action='assign-all-owner'][data-who='Jax']"); pg.wait_for_timeout(300)
        print("ALL modal:", pg.inner_text(".modal-head h3"), "|", pg.inner_text("button[data-action='confirm-owner']"), "| rows:", pg.locator(".modal .confirm-row").count())
        pg.click("button[data-action='confirm-owner']"); pg.wait_for_timeout(600)
        print("after all->Jax unassigned:", unassigned())
        pg.click(".toast-btn"); pg.wait_for_timeout(600); print("after undo all:", unassigned())
        # flip
        pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300)
        pg.locator("button[data-action='flip-owner']").first.click(); pg.wait_for_timeout(300)
        print("flip modal:", pg.inner_text(".modal-head h3")); pg.click("button[data-action='close-modal'] >> text=Cancel")
        # ---- apply to all cost
        pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(300)
        multi = pg.evaluate("""() => { const S = window.__t.state(); const m = {}; S.batches.forEach(b => { const p = S.products.find(x=>x.id===b.productId); if(!p) return; const k=p.name.toLowerCase().replace(/[^a-z0-9]/g,'')+b.owner; (m[k]=m[k]||[]).push(b.id); }); return Object.values(m).filter(a=>a.length>1)[0] || null; }""")
        print("owner-group with 2+ batches:", multi)
        if multi:
            pg.locator(f"button[data-action='edit-batch'][data-id='{multi[0]}']").click(); pg.wait_for_timeout(300)
            print("apply-all box:", pg.locator("#f_applyall").count(), "checked:", pg.is_checked("#f_applyall"))
            pg.fill("#f_cost", "12.34"); pg.click("button[data-action='submit-edit-batch']"); pg.wait_for_timeout(400)
            costs = pg.evaluate("(ids) => ids.map(i => window.__t.state().batches.find(b=>b.id===i).unitCost)", multi)
            print("costs after apply-all:", costs, "| toast:", pg.inner_text("#toastRoot").replace("\n"," "))
        # ---- store trip
        pg.click("button[data-action='open-trip']"); pg.wait_for_timeout(300)
        rows = pg.locator(".trip-row"); print("trip rows:", rows.count())
        pg.click("button[data-action='trip-toggle-all']"); pg.select_option("#t_who", "Jon"); pg.fill("#t_total", "108.50")
        for i, (q, pr) in enumerate([(1, "50"), (2, "25")]):
            r = rows.nth(i); r.locator(".trip-chk").check(); r.locator(".trip-qty").fill(str(q)); r.locator(".trip-price").fill(pr)
        pg.wait_for_timeout(200); print("summary:", pg.inner_text("#tripSummary"))
        pg.screenshot(path=str(out / "v9_trip.png"))
        pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(300)
        print("confirm:", pg.inner_text(".modal-body").replace("\n"," | ")[:420])
        pg.screenshot(path=str(out / "v9_trip_confirm.png"))
        names = pg.evaluate("""() => { const S = window.__t.state(); return null; }""")
        pg.click("button[data-action='trip-apply']"); pg.wait_for_timeout(500)
        print("toast:", pg.inner_text("#toastRoot").replace("\n"," "))
        pg.click(".toast-btn"); pg.wait_for_timeout(400); print("trip undo toast:", pg.inner_text("#toastRoot").replace("\n"," ")[-40:])
        # ---- dashboard
        pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(400)
        print("dash cards:", pg.locator(".dash-card").count(), "| stock rows:", pg.locator(".stk-row").count(), "| split rows:", pg.locator(".split-rows div").count())
        pg.screenshot(path=str(out / "v9_dash.png"), full_page=True)
        print("scrollW", pg.evaluate("document.documentElement.scrollWidth"), "errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_v9_copy.html").unlink(missing_ok=True)
