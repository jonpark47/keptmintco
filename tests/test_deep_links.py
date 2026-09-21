import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
sale_id = next(s["id"] for s in data["sales"] if s.get("createdBy") == "ebay-sync")
for s in data["sales"]:
    if s["id"] == sale_id: s["attributedTo"] = None; s["needsOwner"] = True
zel = next(p for p in data["products"] if "exeggutor" in p["name"].lower())
for b in data["batches"]:
    if b["productId"] == zel["id"]: b["unitCost"] = 0; b["costKnown"] = False
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_d.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8806", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
def load(pg, frag):
    pg.goto("http://localhost:8806/_d.html#" + frag.split("?")[0].lstrip("#")); pg.wait_for_timeout(1500)
    pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
    pg.evaluate("(f) => { location.hash = f; }", frag.lstrip("#")); pg.wait_for_timeout(700)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        load(pg, f"#overview?owner={sale_id}")
        print("owner link -> modal:", pg.inner_text(".modal-head h3") if pg.locator(".modal").count() else None, "| hash cleaned:", pg.evaluate("location.hash"))
        pg.click(".modal button[data-action='assign-owner'][data-who='Jax']"); pg.wait_for_timeout(300)
        print("then:", pg.inner_text(".modal-head h3"))
        load(pg, f"#inventory?cost={zel['id']}")
        print("cost link -> modal:", pg.inner_text(".modal-head h3") if pg.locator(".modal").count() else None, "| tab:", pg.evaluate("document.body.dataset.tab"), "| hash:", pg.evaluate("location.hash"))
        load(pg, "#overview?owner=doesnotexist")
        print("bad id -> toast:", pg.inner_text("#toastRoot").replace("\n", " "))
        load(pg, "#sales")
        print("plain hash ok, modal:", pg.locator(".modal").count())
        print("errors:", errs)
        b.close()
finally:
    srv.terminate(); (root / "_d.html").unlink(missing_ok=True)
