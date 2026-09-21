import re, subprocess, time, pathlib, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},render:render,paint:paintBooksPill}; boot();", 1)
(root / "_bk_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8824", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (390, 320):
            pg = b.new_page(viewport={"width": w, "height": 844}, has_touch=True, is_mobile=True)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8824/_bk_copy.html#overview"); pg.wait_for_timeout(1500)
            print(w, "px, before any check:", repr(pg.inner_text("#booksPill")))
            pg.evaluate("() => { window.__t.state().books = {ok:true, n:0, at:Date.now()-120000, findings:[]}; window.__t.paint(); }")
            print("  all clear:", pg.inner_text("#booksPill"), "| amber:", "stale" in (pg.get_attribute("#booksPill", "class") or ""))
            pg.evaluate("() => { window.__t.state().books = {ok:false, n:3, at:Date.now()-60000, findings:[{code:'nocost',text:'Round 1 x One Piece Collab Club Card Zoro Sanji LOADED With a very long title that has to wrap (tbt_vending): no purchase price'},{code:'nolabel',text:'Pikachu ex (buyer2): no shipping label cost'}]}; window.__t.paint(); }")
            print("  needs you:", pg.inner_text("#booksPill"), "| amber:", "stale" in (pg.get_attribute("#booksPill", "class") or ""))
            pg.click("#booksPill"); pg.wait_for_timeout(250)
            print("  list:", pg.inner_text(".modal-body").replace("\n", " | ")[:330])
            print("  no sideways scroll:", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
            pg.click("button[data-action='close-modal']"); pg.wait_for_timeout(150)
            pg.evaluate("() => { window.__t.state().books = {ok:true, n:0, at:Date.now()-3*3600*1000, findings:[]}; window.__t.paint(); }")
            print("  old check:", pg.inner_text("#booksPill"))
            print("  errors:", errs)
            pg.close()
        b.close()
finally:
    srv.terminate(); (root / "_bk_copy.html").unlink(missing_ok=True)
