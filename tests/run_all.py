#!/usr/bin/env python3
"""Run every browser test against index.html and compare what it reports with the saved expected output.

    python tests/run_all.py            # check (what CI runs)
    python tests/run_all.py --update   # after an INTENTIONAL behaviour change, re-save the expected output

Each test loads a copy of the app offline (Firebase pointed at nothing) with a fixed, anonymised copy of the ledger
(tests/fixture.json), drives it like a person would, and prints what happened. The expected output lives in
tests/expected/. A test fails if it crashes, prints a page error, or its output changes. That is deliberate: any
change in behaviour has to be looked at and either fixed or accepted with --update in the same commit.
"""
import os
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).resolve().parent
EXPECTED = HERE / "expected"
EXPECTED.mkdir(exist_ok=True)
update = "--update" in sys.argv
only = [a for a in sys.argv[1:] if not a.startswith("--")]


def normalise(text):
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", text)  # the run date shows up in export filenames
    return text.strip() + "\n"


env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
failed = []
tests = sorted(HERE.glob("test_*.py"))
for t in tests:
    if only and not any(o in t.name for o in only):
        continue
    try:
        r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, encoding="utf-8", timeout=240, env=env, cwd=str(HERE))
        got, code = normalise(r.stdout + (("\nSTDERR:\n" + r.stderr) if r.stderr.strip() else "")), r.returncode
    except subprocess.TimeoutExpired:
        got, code = "TIMEOUT\n", 1
    problems = []
    if code != 0:
        problems.append(f"exited with code {code}")
    if "Traceback" in got or re.search(r"errors: \[.+\]", got) or "pageerror" in got.lower():
        problems.append("crashed or reported a page error")
    exp_file = EXPECTED / (t.stem + ".txt")
    if update and not problems:
        exp_file.write_text(got, encoding="utf-8", newline="\n")
    elif not exp_file.exists():
        problems.append("no expected output saved (run with --update once)")
    elif exp_file.read_text(encoding="utf-8") != got:
        problems.append("output changed:\n" + "\n".join(
            "      " + l for l in __import__("difflib").unified_diff(exp_file.read_text(encoding="utf-8").splitlines(), got.splitlines(), "expected", "got", lineterm="", n=0)))
    print(("FAIL " if problems else "ok   ") + t.stem)
    for p in problems:
        print("   - " + p)
    if problems:
        failed.append(t.stem)

if failed:
    print(f"\n{len(failed)} of {len(tests)} tests failed: " + ", ".join(failed))
    sys.exit(1)
print(f"\nall {len(tests)} tests passed" + (" (expected output updated)" if update else ""))
