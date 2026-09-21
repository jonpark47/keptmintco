#!/usr/bin/env python3
"""Static checks on index.html, run in CI on every push (needs node/npx for the lint step).

  1. No undefined names in the app script. A function that gets deleted while something still calls it
     shows up here as `no-undef`, instead of as a dead button on Jon's phone.
  2. Every button (`data-action="x"`) that the markup can produce has a click handler, and every handler is
     reachable from some button. A missing handler is a button that silently does nothing.
  3. Every `#id` the script reads with $("#...") exists in the page or is created by the script.

    python tools/check_app.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
blocks = re.findall(r"<script>([\s\S]*?)</script>", html)
js = "\n".join(blocks)
problems = []

# ---- 1. undefined names
tmp = tempfile.mkdtemp()
open(os.path.join(tmp, "app.js"), "w", encoding="utf-8").write(js)
cfg = {"root": True, "env": {"browser": True, "es2020": True}, "parserOptions": {"ecmaVersion": 2020},
       "globals": {"firebase": "readonly"}, "rules": {"no-undef": "error"}}
json.dump(cfg, open(os.path.join(tmp, "eslintrc.json"), "w"))
npx = shutil.which("npx") or shutil.which("npx.cmd")
if not npx:
    problems.append("npx not found; cannot run the undefined-name check")
else:
    r = subprocess.run([npx, "--yes", "eslint@8", "--no-eslintrc", "-c", os.path.join(tmp, "eslintrc.json"), os.path.join(tmp, "app.js"), "-f", "unix"],
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    lines = [l for l in r.stdout.splitlines() if "no-undef" in l]
    for l in lines:
        problems.append("undefined name: " + l.split("app.js:", 1)[-1])
    if r.returncode not in (0, 1) or (r.returncode == 1 and not lines):
        problems.append("eslint itself failed: " + (r.stdout + r.stderr)[-400:])

# ---- 2. buttons vs handlers
used = set(re.findall(r"""data-action=["']([\w-]+)["']""", html))  # html holds the script too
handled = set(re.findall(r"""\baction\s*===?\s*["']([\w-]+)["']""", js))
for a in sorted(used - handled):
    problems.append(f"button data-action='{a}' has no click handler")
for a in sorted(handled - used):
    # handlers wired to a dynamic data-action (built as "+action+") are exempt if the name is passed as a string elsewhere
    if not re.search(r"""["']""" + re.escape(a) + r"""["']""", js.replace(f'action==="{a}"', "").replace(f"action==='{a}'", "").replace(f'action === "{a}"', "")):
        problems.append(f"click handler '{a}' is not reachable from any button")

# ---- 3. element ids the script depends on
page_ids = set(re.findall(r"""\bid\s*=\s*\\?["']?([\w-]+)""", html)) | set(re.findall(r"""\.id\s*=\s*["']([\w-]+)["']""", js))
for i in sorted(set(re.findall(r"""\$\(["']#([\w-]+)""", js)) - page_ids):
    problems.append(f"the script looks up #{i}, which the page never creates")

if problems:
    print("APP CHECK FAILED")
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print(f"app check ok: no undefined names, {len(used)} button actions all handled, ids resolve")
