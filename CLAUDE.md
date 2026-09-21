# KeptMint -- project rules

Single-file app (`index.html`) on GitHub Pages, data in Firestore project `keptmintco`. See the op-news-bot
repo's HANDOFF.md for the eBay sync and the Discord alert feed that sit on the VPS.

## Hard rules

- **Never delete code by line range or string slicing without re-reading the seams.** Every removal (a function,
  a button handler, a file) must be declared in the commit message on a line like
  `Removes: openOldImport, action:import-csv` -- CI's `tools/check_removals.py` fails the push otherwise. Run
  `python tools/check_removals.py HEAD~1 HEAD` before pushing.
- **Run `python tools/check_app.py` and `python tests/run_all.py` before pushing.** The first catches a deleted
  function that is still called and a button with no handler. The second replays the real flows on a phone-sized
  screen against an anonymised copy of the ledger (`tests/fixture.json`) and fails if anything they report
  changes. If a change in behaviour is intended, look at the diff, then `python tests/run_all.py --update` and
  commit the new `tests/expected/` files in the same commit.
- **A new feature gets a test in `tests/`** (copy the closest `test_*.py`), and `run_all.py --update` once.
- **Never commit the real ledger.** `tests/fixture.json` has buyer names replaced and money scaled; keep it that way.
- No em-dashes in code comments, copy or commit messages.
