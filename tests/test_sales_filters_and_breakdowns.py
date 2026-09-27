import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
# The fixture ships with every sale still pending. Mark a handful of each owner "completed" (eBay
# actually paid out), oldest-dated first, so status/owner dropdowns and the debt allocation both
# have something real to work with.
jon = sorted([s for s in data["sales"] if s["attributedTo"] == "Jon"], key=lambda s: s["saleDate"])
jax = [s for s in data["sales"] if s["attributedTo"] == "Jax"]
for s in jon[:4]: s["lifecycleStatus"] = "completed"
for s in jax[:2]: s["lifecycleStatus"] = "completed"
paid_jon, paid_jax = jon[:4], jax[:2]
pending_jon, pending_jax = len(jon) - len(paid_jon), len(jax) - len(paid_jax)
jon_paid_total = round(sum(s["netProfit"] for s in paid_jon), 2)
# Jax has already handed over enough to fully cover the two oldest of Jon's paid sales, and part
# of the third -- exercises "settled", "partial" and "owed" all in one allocation.
covered_target = round(paid_jon[0]["netProfit"] + paid_jon[1]["netProfit"] + paid_jon[2]["netProfit"] / 2, 2)
data["settlements"] = [{"id": "st1", "from": "Jax", "to": "Jon", "amount": covered_target, "date": "2026-09-15", "note": "test settlement", "createdAt": 1}]
still_owed = round(jon_paid_total - covered_target, 2)

html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_sfb.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8811", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)


def seed(pg, frag):
    pg.goto("http://localhost:8811/_sfb.html#" + frag.lstrip("#")); pg.wait_for_timeout(1200)
    pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
    pg.wait_for_timeout(300)


try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        seed(pg, "#sales")

        # ---- dropdowns replace the chip wall, and still combine
        print("dropdown options, status:", pg.eval_on_selector_all("#salesStatusSelect option", "els => els.map(e => e.textContent)"))
        print("dropdown options, owner:", pg.eval_on_selector_all("#salesOwnerSelect option", "els => els.map(e => e.textContent)"))
        pg.select_option("#salesStatusSelect", "paid")
        pg.select_option("#salesOwnerSelect", "Jon")
        print("paid+Jon: rows", pg.locator(".sale-row").count(), "| want", len(paid_jon))
        print("summary:", pg.inner_text(".filter-summary").replace("\n", " "), "| want total", jon_paid_total)
        pg.select_option("#salesOwnerSelect", "Jax")
        print("paid+Jax: rows", pg.locator(".sale-row").count(), "| want", len(paid_jax))
        pg.select_option("#salesStatusSelect", "pending")
        print("pending+Jax: rows", pg.locator(".sale-row").count(), "| want", pending_jax)

        # ---- mini stat tiles on Sales are themselves clickable shortcuts
        pg.click(".tiles.mini .tile.t-brand")
        print("tap 'Paid out' tile -> status:", pg.eval_on_selector("#salesStatusSelect", "e => e.value"), "| owner reset:", pg.eval_on_selector("#salesOwnerSelect", "e => e.value"))

        # ---- Overview's tiles jump tabs AND filter, in one click
        seed(pg, "#overview")
        pg.click(".tiles .tile.t-pending")
        print("Overview 'Pending payout' tile -> tab:", pg.evaluate("document.body.dataset.tab"), "| status:", pg.eval_on_selector("#salesStatusSelect", "e => e.value"))

        # ---- Settlements: the debt tile drills into exactly which orders, oldest-paid-first,
        # each tagged settled / partially paid / still owed, and the "still owed" total matches
        # the tile's own headline number.
        seed(pg, "#settlements")
        before_tab = pg.evaluate("document.body.dataset.tab")
        pg.click(".tile[data-action='open-debt-breakdown']")
        print("debt modal open, tab unchanged:", pg.evaluate("document.body.dataset.tab") == before_tab)
        badges = pg.eval_on_selector_all(".modal-body .sale-row .badge.settle-done, .modal-body .sale-row .badge.settle-partial, .modal-body .sale-row .badge.settle-owed", "els => els.map(e => e.className.match(/settle-\\w+/)[0])")
        print("debt allocation badges, oldest-paid-first:", badges, "| want first 2 settled, 1 partial, rest owed")
        print("debt modal footer:", pg.inner_text(".modal-foot").replace("\n", " "), "| want still-owed total", still_owed)
        pg.click(".modal-foot button[data-action='close-modal']")

        # ---- keyboard activation on a role=button tile (not a real <button>)
        pg.click("body")  # drop any focus first
        pg.locator(".tile[data-action='open-debt-breakdown']").focus()
        pg.keyboard.press("Enter")
        print("Enter on debt tile opens modal:", pg.locator(".modal").count() > 0)
        pg.keyboard.press("Escape")
        print("Escape closes it:", pg.locator(".modal").count())

        # ---- "Your payout" tile -> every one of the viewer's own sales, pending and paid alike
        pg.click(".tile[data-action='open-owner-breakdown'][data-owner='Jon']")
        print("Your payout modal rows:", pg.locator(".modal-body .sale-row").count(), "| want", len(jon))
        pg.click(".modal-foot button[data-action='close-modal']")

        print("errors:", errs, "| scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_sfb.html").unlink(missing_ok=True)
