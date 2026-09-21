#!/usr/bin/env python3
"""Fail a change that REMOVES something without saying so.

On 2026-09-20 a cleanup deleted the `@client.event` line above `on_message`, and nothing noticed for 8
hours. Deleting is fine; deleting BY ACCIDENT is the problem. This guard compares two commits and lists
everything that disappeared:

  - functions / classes / methods (Python), and `function name(` in JS / HTML
  - a decorator that a surviving function lost (Python)
  - `data-action` click handlers (JS / HTML)
  - whole source files (.py .js .html .yml)

Each removal must be DECLARED in a commit message in the range, on a line like:

    Removes: on_message decorator, _handle_ebay_drop, ebay_import_poll.py

(names are matched case-insensitively; a name that reappears elsewhere in the same change counts as
moved, not removed.) Anything undeclared fails.

    python tools/check_removals.py BASE HEAD        # e.g. HEAD~1 HEAD, or the push's before/after
"""
import ast
import re
import subprocess
import sys

SOURCE_EXT = (".py", ".js", ".html", ".yml", ".yaml")
SKIP_PARTS = ("tests/out/", "node_modules/", "__pycache__/")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def changed_files(base, head):
    out = git("diff", "--name-status", "--no-renames", base, head)
    rows = [l.split("\t") for l in out.splitlines() if l.strip()]
    return [(r[0], r[1]) for r in rows if len(r) >= 2 and r[1].endswith(SOURCE_EXT) and not any(p in r[1] for p in SKIP_PARTS)]


def show(rev, path):
    return subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def py_symbols(src):
    """{qualified name: [decorators]} for every function, method and class"""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    out = {}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = prefix + child.name
                out[q] = [ast.unparse(d) for d in child.decorator_list]
                walk(child, q + ".")
    walk(tree)
    return out


def js_symbols(src):
    """function names and data-action handlers found in JS / HTML / inline script text"""
    names = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", src))
    actions = set(re.findall(r"action\s*===?\s*[\"']([\w-]+)[\"']", src))
    return names, {"action:" + a for a in actions}


def declared(base, head):
    text = git("log", "--format=%B", f"{base}..{head}")
    names = set()
    for line in text.splitlines():
        m = re.match(r"\s*removes\s*:\s*(.+)$", line, re.I)
        if m:
            for tok in re.split(r"[,;]", m.group(1)):
                tok = tok.strip().lower()
                if tok:
                    names.add(tok)
                    names.add(tok.split()[0])  # "on_message decorator" also matches "on_message"
    return names


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    base, head = sys.argv[1], sys.argv[2]
    ok = declared(base, head)
    removed, added = [], set()          # removed: (path, what, kind)  kind = file | symbol | decorator
    for status, path in changed_files(base, head):
        if status == "D":
            removed.append((path, path, "file"))
            continue
        new_src = show(head, path)
        old_src = "" if status == "A" else show(base, path)
        if path.endswith(".py"):
            old, new = py_symbols(old_src), py_symbols(new_src)
            added |= {n.lower() for n in new}
            for name in old:
                if name not in new:
                    removed.append((path, name, "symbol"))
                elif not set(old[name]) <= set(new[name]):
                    removed.append((path, name, "decorator"))
        elif path.endswith((".js", ".html")):
            (on, oa), (nn, na) = js_symbols(old_src), js_symbols(new_src)
            added |= {n.lower() for n in nn | na}
            for name in sorted(on - nn) + sorted(oa - na):
                removed.append((path, name, "symbol"))
    bad = []
    for path, what, kind in removed:
        key = what.lower()
        bare = key.split(".")[-1].replace("action:", "")
        if key in ok or bare in ok or path.lower() in ok or path.split("/")[-1].lower() in ok:
            continue
        if kind == "symbol" and key in added:
            continue  # moved to another file (or another spot), not removed
        bad.append((path, what, kind))
    if bad:
        print("UNDECLARED REMOVALS -- if this is intended, add a line like 'Removes: <name>, <name>' to the commit message:")
        for path, what, kind in bad:
            label = {"file": "file deleted", "symbol": "removed", "decorator": "lost a decorator"}[kind]
            print(f"  - {path}: {what} ({label})")
        sys.exit(1)
    print(f"removals check ok ({len(removed)} removal(s), all declared or moved)")


if __name__ == "__main__":
    main()
