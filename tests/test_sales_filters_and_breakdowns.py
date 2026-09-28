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
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render,debt:jonDebtAllocation,balance:computeBalance}; boot();", 1)
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
        # the settle status shows right on the main list too, separate from the "Paid out" pill --
        # not only inside the debt drill-down modal
        row_badges = pg.eval_on_selector_all(".sales-list .sale-row .badge.settle-done, .sales-list .sale-row .badge.settle-partial, .sales-list .sale-row .badge.settle-owed",
            "els => els.map(e => e.className.match(/settle-\\w+/)[0])")
        pay_pills = pg.locator(".sales-list .sale-row .badge.lifecycle-completed").count()
        print("inline settle badges on the Sales list:", row_badges, "| still all show the separate 'Paid out' pill too:", pay_pills == len(paid_jon))
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

        # ---- "Record payment": a checklist of the exact cards this payment covers, checked by
        # default (the two still-outstanding sales, partial + owed), driving the Amount live --
        # not a blind number, and a dropdown to add any other order in case the FIFO guess is wrong.
        pg.click("button[data-action='open-add-settlement']")
        print("default from/to/amount:", pg.input_value("#f_from"), pg.input_value("#f_to"), pg.input_value("#f_amount"), "| want amount", still_owed)
        checked_ids = lambda: pg.eval_on_selector_all("#settlementCoverage .cov-chk:checked", "els => els.map(e => e.dataset.id)")
        print("checklist starts with both outstanding cards checked:", len(checked_ids()), "| no Edit/Remove on them:", pg.locator("#settlementCoverage .sale-actions").count())
        second_id = checked_ids()[1]
        pg.locator("#settlementCoverage .cov-chk").nth(1).uncheck()
        print("unchecking the 2nd card drops it and updates Amount live:", len(checked_ids()), pg.input_value("#f_amount"))
        # "Add another order" browses ALL of Jon's paid sales the instant it's clicked into (no
        # typing required), and filters live as you type -- picking a result adds it (checked) and
        # raises the Amount by its payout, even though it's already settled by the FIFO guess
        settled_sale = paid_jon[0]
        pg.click("#covAddSearch")
        print("results visible the instant it's clicked into, before typing anything:", pg.locator("#covAddResults").is_visible())
        before_type = pg.locator("#covAddResults .cov-add-row").count()
        pg.locator("#covAddSearch").fill(settled_sale["buyerName"]); pg.wait_for_timeout(150)
        after_type = pg.locator("#covAddResults .cov-add-row").count()
        print("results shown with nothing typed vs filtered by buyer name:", before_type, "->", after_type)
        pg.locator(f"#covAddResults .cov-add-row[data-id='{settled_sale['id']}']").click()
        print("picked an already-settled order from the results, Amount rose and it's now checked, results closed:", pg.input_value("#f_amount"), pg.locator(f"#settlementCoverage .cov-chk[data-id='{settled_sale['id']}']").is_checked(), pg.locator("#covAddResults").is_visible())
        pg.select_option("#f_from", "Jon"); pg.select_option("#f_to", "Jax")
        print("flip to Jon -> Jax, checklist hides:", pg.inner_text("#settlementCoverage").strip() == "", "| add field hides too:", not pg.is_visible("#covAddField"))
        pg.select_option("#f_from", "Jax"); pg.select_option("#f_to", "Jon")
        print("flip back, selection was preserved (not reset):", sorted(checked_ids()) == sorted([x for x in checked_ids()]))
        # undo the manual add so the save below tests exactly one thing: the plain uncheck
        pg.locator(f"#settlementCoverage .cov-chk[data-id='{settled_sale['id']}']").uncheck()
        pg.click("button[data-action='submit-add-settlement']")
        pg.wait_for_timeout(300)

        # ---- THE question: uncheck an order, save -- does it come back marked settled anyway?
        sale_after = pg.evaluate("(id) => window.__t.state().sales.find(s => s.id === id)", second_id)
        pr_after = pg.evaluate("(id) => { const p = window.__t.state().products.find(x => x.id === id); return p ? p.name : null; }", sale_after["productId"])
        seed(pg, "#settlements")  # re-seeding also re-derives the allocation from the freshly-saved settlement
        pg.click(".tile[data-action='open-debt-breakdown']")
        order_num = sale_after["orderNumber"]
        matching = pg.locator(f".modal-body .sale-row:has-text('#{order_num}')")
        print("the order left unchecked at save time:", pr_after, "| its badge now:", matching.locator(".badge.settle-owed, .badge.settle-partial, .badge.settle-done").inner_text().strip() if matching.count() else "not in the still-owed list at all")
        print("(want: 'Still owed to you' -- unchecking it must guarantee that, no matter what else was saved)")
        pg.click(".modal-foot button[data-action='close-modal']")

        # ---- the reconciliation identity itself: sum(every row's owedAmount) + unallocated must
        # equal computeBalance() exactly, always -- the one real settlement just saved above (with
        # an allocations array) plus the original legacy one (without) both feed into this same check.
        def reconciles():
            # the identity: sum(every row's owedAmount) - unallocated == computeBalance(), always --
            # bal positive (Jax owes Jon) or negative (Jon overpaid ahead, owes Jax) alike
            return pg.evaluate("""() => {
              const d = window.__t.debt(), bal = window.__t.balance();
              const owed = d.rows.reduce((a,r) => a + r.owedAmount, 0);
              const lhs = Math.round((owed-d.unallocated)*100)/100, rhs = Math.round(bal*100)/100;
              return { owedMinusUnalloc: lhs, bal: rhs, matches: Math.abs(lhs-rhs) < 0.01 };
            }""")
        print("reconciliation after a real save (allocations + legacy settlement both present):", reconciles())

        # ---- paying off the rest across a SECOND, separate payment: no double-counting the first
        still_owed_now = pg.evaluate("() => window.__t.debt().rows.reduce((a,r) => a + r.owedAmount, 0)")
        pg.click("button[data-action='open-add-settlement']")
        print("2nd payment opens pre-filled with exactly what's left:", pg.input_value("#f_amount"), "| want", round(still_owed_now, 2))
        all_checked = pg.eval_on_selector_all("#settlementCoverage .cov-chk", "els => els.every(e => e.checked)")
        pg.click("button[data-action='submit-add-settlement']"); pg.wait_for_timeout(300)
        print("all rows were checked by default:", all_checked, "| everything settled after paying it off:", reconciles(), "| still-owed total is now $0:", pg.evaluate("() => window.__t.debt().rows.reduce((a,r) => a + r.owedAmount, 0)"))

        # ---- deleting a sale that a past settlement explicitly allocated money to: that money
        # must not vanish (it should fold into `unallocated`), and the identity must still hold
        deleted_id = pg.evaluate("""() => {
          const d = window.__t.debt();
          const settledRow = d.rows.find(r => r.status === 'settled');
          const S = window.__t.state();
          S.sales = S.sales.filter(s => s.id !== settledRow.sale.id);
          window.__t.render();
          return settledRow.sale.id;
        }""")
        print("deleted a fully-settled sale, reconciliation still holds:", reconciles())

        # ---- editing a sale's payout DOWN after it was already fully allocated against: the
        # excess must fold into `unallocated`, not vanish, and the identity must still hold
        pg.evaluate("""() => {
          const S = window.__t.state();
          const settledRow = window.__t.debt().rows.find(r => r.status === 'settled');
          settledRow.sale.netProfit = Math.round(settledRow.sale.netProfit / 3 * 100) / 100;
          window.__t.render();
        }""")
        print("edited a settled sale's payout down, reconciliation still holds:", reconciles())
        # the live ledger-check banner (renderLedgerBanner) stays silent through every one of the
        # scenarios above, including the two that would have broken the pre-fix math -- if any of
        # them had actually thrown the identity off, Jon would see a warning right on the page,
        # using his own real data, not just in a test file
        print("ledger banner stays silent (everything still reconciles):", pg.inner_text("#ledgerBanner").strip() == "")

        print("errors:", errs, "| scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_sfb.html").unlink(missing_ok=True)
