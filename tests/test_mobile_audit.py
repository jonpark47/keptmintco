"""Strict mobile audit: page overflow, inner horizontal scrollers, clipped content, and text that
spills out of the card/tile it sits in. Uses stress data (big money, long names) on every tab
and on every modal the app can open."""
import re, subprocess, time, pathlib, sys, json, copy
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
root = HERE.parent
out = HERE / "out"
out.mkdir(exist_ok=True)
data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
# stress: bigger money and longer names so any fragile layout shows up
for s in data["sales"]:
    s["netProfit"] = round(float(s.get("netProfit") or 0) * 23.7 + 1234.56, 2)
    s["buyerName"] = (s.get("buyerName") or "buyer") + "_the_longest_username_ever_12"
for p in data["products"]:
    p["name"] = p["name"] + " - Extra Long Marketplace Title Variant Edition"
for b in data["batches"]:
    b["unitCost"] = round(float(b.get("unitCost") or 0) * 9.3 + 111.11, 2)
    b["costKnown"] = True

html = (root / "index.html").read_text(encoding="utf-8")
html = re.sub(r"var firebaseConfig = \{[\s\S]*?\n  \};", 'var firebaseConfig = {apiKey:"invalid",authDomain:"invalid.firebaseapp.com",projectId:"invalid-offline-test"};', html)
html = html.replace("boot();", "window.__t={state:function(){return state;},setTab:setTab,render:render}; boot();", 1)
(root / "_m_copy.html").write_text(html, encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8801", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)

PROBE = r"""() => {
  const vw = document.documentElement.clientWidth, res = { vw, doc: document.documentElement.scrollWidth, scrollers: [], clipped: [], spill: [] };
  const cn = e => (e && e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).slice(0,2).join('.') : (e ? e.tagName.toLowerCase() : ''));
  const name = e => (e.className && typeof e.className === 'string' && e.className.trim() ? cn(e) : cn(e.parentElement) + '>' + e.tagName.toLowerCase());
  document.querySelectorAll('body *').forEach(e => {
    const cs = getComputedStyle(e); const r = e.getBoundingClientRect();
    if (!r.width || cs.display === 'none' || cs.visibility === 'hidden') return;
    if ((cs.overflowX === 'auto' || cs.overflowX === 'scroll') && e.scrollWidth > e.clientWidth + 1) res.scrollers.push(name(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
    if ((cs.overflowX === 'hidden' || cs.overflowX === 'clip') && e.scrollWidth > e.clientWidth + 1 && e !== document.body && !e.classList.contains('tile') && e.tagName !== 'INPUT' && e.tagName !== 'TEXTAREA') res.clipped.push(name(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  });
  // text leaving the box it sits in (nearest ancestor that draws a background or border)
  const draws = e => { const cs = getComputedStyle(e); const bg = cs.backgroundColor; return (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') || cs.backgroundImage !== 'none' || (parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== 'none'); };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.nodeValue.trim()) continue;
    const el = n.parentElement; if (!el || ['SCRIPT','STYLE','OPTION'].includes(el.tagName)) continue;
    const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const rects = Array.from(range.getClientRects()).filter(x => x.width > 0);
    if (!rects.length) continue;
    let box = el; while (box && box !== document.body && !draws(box)) box = box.parentElement;
    if (!box || box === document.body) box = null;
    for (const t of rects) {
      if (t.right > vw + 0.5 || t.left < -0.5) { res.spill.push('OFFSCREEN ' + name(el) + ' "' + n.nodeValue.trim().slice(0,26) + '" right=' + Math.round(t.right)); break; }
      if (box) { const b = box.getBoundingClientRect(); const bcs = getComputedStyle(box);
        if (bcs.position === 'fixed') continue;
        if (t.right > b.right + 0.5 || t.left < b.left - 0.5) { res.spill.push(name(box) + ' > ' + name(el) + ' "' + n.nodeValue.trim().slice(0,26) + '" text ' + Math.round(t.right) + ' box ' + Math.round(b.right)); break; } }
    }
  }
  res.scrollers = Array.from(new Set(res.scrollers)).slice(0, 8); res.clipped = Array.from(new Set(res.clipped)).slice(0, 8); res.spill = Array.from(new Set(res.spill)).slice(0, 12);
  return res;
}"""

MODALS = [
    ("add-sale", "open-add-sale"), ("add-batch", "open-add-batch"), ("edit-batch", "edit-batch"), ("edit-sale", "edit-sale"),
    ("trip", "open-trip"), ("cost-one", "cost-one"), ("add-settlement", "open-add-settlement"),
]

issues = {}
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h in ((320, 640), (360, 740), (375, 812), (390, 844), (412, 915), (430, 932)):
            ctx = b.new_context(viewport={"width": w, "height": h}, has_touch=True, is_mobile=True); pg = ctx.new_page()
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:8801/_m_copy.html"); pg.wait_for_timeout(1500)
            pg.evaluate("(d) => { const S = window.__t.state(); ['products','batches','sales','settlements'].forEach(k => { S[k] = d[k]; }); window.__t.render(); }", data)
            cdp = ctx.new_cdp_session(pg)
            for tab in ("overview", "inventory", "insights", "sales", "settlements"):
                pg.evaluate("t => window.__t.setTab(t)", tab); pg.wait_for_timeout(300)
                for yy in (150, 300, 450, 600):
                    for x0, x1 in ((w - 30, 30), (30, w - 30)):
                        yv = min(yy, h - 120)
                        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": yv}]})
                        for i in range(1, 11):
                            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * i / 10, "y": yv}]}); time.sleep(0.01)
                        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                pg.wait_for_timeout(200)
                moved = pg.evaluate("() => { const m = []; if (window.scrollX) m.push('window ' + window.scrollX); document.querySelectorAll('*').forEach(e => { if (e.scrollLeft > 0) m.push((e.className||e.tagName) + ' ' + e.scrollLeft); }); return m.slice(0,6); }")
                if moved: issues[f"{w} swipe:{tab}"] = {"scrollers": moved}
                r = pg.evaluate(PROBE)
                bad = (r["doc"] > r["vw"]) or r["scrollers"] or r["clipped"] or r["spill"]
                if bad: issues[f"{w} {tab}"] = {"doc": r["doc"] if r["doc"] > r["vw"] else None, "scrollers": r["scrollers"], "clipped": r["clipped"], "spill": r["spill"]}
            # modals
            for label, action in MODALS:
                pg.evaluate("window.__t.setTab('inventory')" if action not in ("edit-sale", "open-add-sale", "open-add-settlement") else ("window.__t.setTab('sales')" if action != "open-add-settlement" else "window.__t.setTab('settlements')"))
                pg.wait_for_timeout(250)
                loc = pg.locator(f"[data-action='{action}']")
                if not loc.count(): continue
                try:
                    loc.first.click(timeout=2000); pg.wait_for_timeout(300)
                except Exception:
                    continue
                r = pg.evaluate(PROBE)
                bad = (r["doc"] > r["vw"]) or r["scrollers"] or r["clipped"] or r["spill"]
                if bad: issues[f"{w} modal:{label}"] = {"doc": r["doc"] if r["doc"] > r["vw"] else None, "scrollers": r["scrollers"], "clipped": r["clipped"], "spill": r["spill"]}
                pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
            # ---- phase 2: prompts, confirms, missing-cost panels, long toasts
            pg.evaluate("""() => { const S = window.__t.state();
              S.sales.slice(0, 6).forEach(sa => { sa.attributedTo = null; sa.needsOwner = true; sa.ownerSource = 'auto'; });
              S.batches.slice(0, 5).forEach(b => { b.unitCost = 0; b.costKnown = false; b.needsReview = true; });
              window.__t.render(); }""")
            def probe_state(label):
                r = pg.evaluate(PROBE)
                if (r["doc"] > r["vw"]) or r["scrollers"] or r["clipped"] or r["spill"]:
                    issues[f"{w} {label}"] = {"doc": r["doc"] if r["doc"] > r["vw"] else None, "scrollers": r["scrollers"], "clipped": r["clipped"], "spill": r["spill"]}
            pg.evaluate("window.__t.setTab('overview')"); pg.wait_for_timeout(300); probe_state("state:overview-with-prompts")
            for label, sel in (("owner-confirm", "#ownerBanner [data-action='assign-owner']"), ("owner-all", "#ownerBanner [data-action='assign-all-owner']"),
                               ("bought-even", "#ownerBanner [data-action='bought-even']"), ("bought-custom", "#ownerBanner [data-action='bought-split']"),
                               ("cost-all", "#costBanner [data-action='cost-all']"), ("cost-one", "#costBanner [data-action='cost-one']")):
                loc = pg.locator(sel)
                if not loc.count(): continue
                try: loc.first.click(timeout=2000); pg.wait_for_timeout(300)
                except Exception: continue
                probe_state("modal:" + label)
                if label == "cost-all":
                    try: pg.click("button[data-action='trip-review']"); pg.wait_for_timeout(400); probe_state("modal:trip-flagged")
                    except Exception: pass
                pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
            pg.evaluate("window.__t.setTab('sales')"); pg.wait_for_timeout(300); probe_state("state:sales-with-prompts")
            pg.evaluate("window.__t.setTab('inventory')"); pg.wait_for_timeout(300); probe_state("state:inventory-with-missing")
            pg.evaluate("""() => { document.querySelector('#toastRoot').insertAdjacentHTML('beforeend', "<div class='toast'>" + "Saved and a very long message to stress the toast width ".repeat(3) + " <button class='toast-btn'>Undo</button></div>"); }""")
            pg.wait_for_timeout(200); probe_state("state:long-toast")
            if errs: issues[f"{w} JS errors"] = errs[:3]
            ctx.close()
        b.close()
finally:
    srv.terminate(); (root / "_m_copy.html").unlink(missing_ok=True)

import collections
sig = collections.OrderedDict()
def norm(x): return re.sub(r"\d+", "#", x)
for k, v in issues.items():
    where = k.split(" ", 1)[1]
    for kk, vv in v.items():
        if not vv: continue
        for item in (vv if isinstance(vv, list) else [vv]):
            sig.setdefault((kk, norm(str(item))), set()).add(where)
if not sig: print("NO ISSUES at any width/tab/modal")
for (kk, item), wh in sig.items():
    print(f"[{kk}] {item}   <- {', '.join(sorted(wh))[:110]}")
