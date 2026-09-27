import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
# The fixture ships with every sale still pending. Mark a handful of each owner "completed" (eBay
# actually paid out) so Paid out / Jon / Jax and their combinations have something real to filter.
jon = [s for s in data["sales"] if s["attributedTo"] == "Jon"]
jax = [s for s in data["sales"] if s["attributedTo"] == "Jax"]
for s in jon[:4]: s["lifecycleStatus"] = "completed"
for s in jax[:2]: s["lifecycleStatus"] = "completed"
paid_jon, paid_jax = len(jon[:4]), len(jax[:2])
pending_jon, pending_jax = len(jon) - paid_jon, len(jax) - paid_jax

html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_pof.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8809", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)


def seed(pg, frag):
    pg.goto("http://localhost:8809/_pof.html#" + frag.lstrip("#")); pg.wait_for_timeout(1200)
    pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
    pg.wait_for_timeout(300)


def chip_on(pg, sel):
    return "on" in (pg.get_attribute(sel, "class") or "")


def rows_count(pg):
    return pg.locator(".sale-row").count()


try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        seed(pg, "#sales")
        print("start: rows", rows_count(pg), "of", len(data["sales"]))

        # status and owner chips are independent -- picking one must not reset the other
        pg.click(".fchip[data-action='sales-filter'][data-f='paid']")
        pg.click(".fchip[data-action='sales-owner-filter'][data-f='Jon']")
        print("paid+Jon: rows", rows_count(pg), "want", paid_jon,
              "| status chip on:", chip_on(pg, ".fchip[data-action='sales-filter'][data-f='paid']"),
              "| owner chip on:", chip_on(pg, ".fchip[data-action='sales-owner-filter'][data-f='Jon']"))

        pg.click(".fchip[data-action='sales-owner-filter'][data-f='Jax']")
        print("paid+Jax: rows", rows_count(pg), "want", paid_jax)

        pg.click(".fchip[data-action='sales-filter'][data-f='pending']")
        print("pending+Jax: rows", rows_count(pg), "want", pending_jax)

        pg.click(".fchip[data-action='sales-owner-filter'][data-f='all']")
        print("pending+everyone: rows", rows_count(pg), "want", pending_jon + pending_jax + 3)  # +3 unassigned

        # owner chip counts should narrow to the active status filter, not always show the grand total
        jon_badge = pg.inner_text(".fchip[data-action='sales-owner-filter'][data-f='Jon'] b")
        print("owner chip count under 'pending':", jon_badge, "want", str(pending_jon))
        pg.click(".fchip[data-action='sales-filter'][data-f='paid']")
        jon_badge2 = pg.inner_text(".fchip[data-action='sales-owner-filter'][data-f='Jon'] b")
        print("owner chip count under 'paid':", jon_badge2, "want", str(paid_jon))

        # the deep link a settlements tile links to: one hop straight to "paid, mine"
        seed(pg, "#sales?paidowner=Jax")
        print("deep link paidowner=Jax: rows", rows_count(pg), "want", paid_jax,
              "| status chip on:", chip_on(pg, ".fchip[data-action='sales-filter'][data-f='paid']"),
              "| owner chip on:", chip_on(pg, ".fchip[data-action='sales-owner-filter'][data-f='Jax']"),
              "| tab:", pg.evaluate("document.body.dataset.tab"))

        # the Settlements page actually carries the links, and they point at the right owner
        seed(pg, "#settlements")
        links = pg.eval_on_selector_all(".tile a.btn", "els => els.map(e => e.getAttribute('href'))")
        print("settlements links:", links)

        print("errors:", errs, "| scrollW", pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
finally:
    srv.terminate(); (root / "_pof.html").unlink(missing_ok=True)
