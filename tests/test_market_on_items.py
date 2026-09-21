import re, subprocess, time, pathlib, sys, json
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_mk_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8818", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (390, 320):
            pg = b.new_page(viewport={"width": w, "height": 844}, has_touch=True, is_mobile=True)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8818/_mk_copy.html#insights"); pg.wait_for_timeout(1500)
            pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); S.sales.forEach((s,i)=>{ if(!s.attributedTo) s.attributedTo='Jon'; }); window.__t.render(); }", data)
            pg.wait_for_timeout(300)
            names = pg.locator(".ins-name").all_inner_texts()
            key = lambda n: re.sub(r"[^a-z0-9]", "", n.lower())
            print(w, "px, before any tracking: market lines:", pg.locator(".ins-market").count())
            pg.evaluate("""(keys) => { const S = window.__t.state(); S.market = {};
              S.market[keys[0]] = {q:'x', cleared:150, perDay:2, supply:40, units1:2, units7:9, units30:31, tracked1:true, tracked7:true, tracked30:false, at:Date.now()-3*3600*1000};
              S.market[keys[1]] = {q:'y', cleared:null, at:Date.now()};
              window.__t.render(); }""", [key(names[0]), key(names[1])])
            pg.wait_for_timeout(300)
            lines = [t.replace("\n", " | ") for t in pg.locator(".ins-market").all_inner_texts()]
            print("  market lines:", len(lines))
            print("  first:", re.sub(r"\$\d[\d,]*\.\d\d", "$X", lines[0]))
            print("  second:", lines[1])
            print("  no sideways scroll:", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "| errors:", errs)
            pg.close()
        b.close()
finally:
    srv.terminate(); (root / "_mk_copy.html").unlink(missing_ok=True)
