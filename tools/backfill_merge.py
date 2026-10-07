"""One-off: merge the verified historical backfill into draw_history.json.

Input: a JSON file {"lotto_649": [{"date": "YYYY-MM-DD", "numbers": [...], "bonus": n}, ...],
                    "lotto_max": [...]}
built in October 2026 from:
  * Loto-Québec yearly "results for past years" pages (Lotto 6/49 1982-2025, Lotto Max 2009-2025)
  * WCLC past winning numbers, last 13 months (Oct 2025 - Oct 2026)
The two sources agreed on every overlapping draw, and the draw counts match WCLC's own
draw numbers (Lotto Max #1276 = Oct 6, 2026; Lotto 6/49 #4402 = Mar 28, 2026).

Existing records (with jackpot / Gold Ball details) always win; backfill only adds missing dates.
Usage: python tools/backfill_merge.py merged.json
"""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")
import main  # noqa: E402

src = json.load(open(sys.argv[1], encoding="utf-8"))
history = main.load_history()
added = {}
for game in ("lotto_max", "lotto_649"):
    have = {main.iso_date(r["date"]) for r in history[game]}
    n = 0
    for r in src[game]:
        if r["date"] in have:
            continue
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        history[game].append({"date": dt.strftime("%A, %B %d, %Y"), "numbers": sorted(r["numbers"]), "bonus": r["bonus"]})
        n += 1
    history[game] = main.normalize_records(history[game])
    added[game] = n
history.setdefault("meta", {})["backfill"] = {
    "added": "2026-10-07",
    "sources": [
        "Loto-Québec, results for past years (loteries.lotoquebec.com), Lotto 6/49 1982-2025 and Lotto Max 2009-2025",
        "WCLC past winning numbers (wclc.com), October 2025 - October 2026",
    ],
    "note": "Cross-checked: both sources agree on all overlapping draws; draw counts match WCLC draw numbers.",
}
main.save_history(history)
print("added", added, "totals", {g: len(history[g]) for g in ("lotto_max", "lotto_649")})
