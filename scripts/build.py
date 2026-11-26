#!/usr/bin/env python3
"""Pull code.golf's full solutions feed and build the Humans-vs-AI datasets.

Writes JSON files ({"rows": [...]}) into the output folder (default: out/):
  weekly.json      week, ai_leads, human_leads, tied, ai_only, human_only
  cells.json       hole, category, lang, status          (today)
  hole_month.json  hole, category, date, ai_lead_pct, human_lead_pct, tied_pct
  lang_month.json  lang, date, ai_held_pct, tied_pct, human_held_pct, holes_solved
  recent.json      latest record changes: when, hole, lang, golfer, side, kind, bytes, prev_*
  meta.json        updated_at, solutions, ai_accounts

Only the Python standard library is used.
"""
import bisect
import datetime as dt
import json
import os
import sys
import urllib.request

BASE = "https://code.golf"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "out")
START = dt.date(2025, 1, 6)  # first week shown
RECENT_DAYS = 14             # how far back "recent changes" looks
RECENT_MAX = 300             # most rows kept in recent.json
UA = {"User-Agent": "codegolf-war-dashboard (github actions)"}


def get_json(path):
    with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=120) as r:
        return json.load(r)


def stream_feed():
    """Yield one solution dict at a time from the (very large) all-solutions feed."""
    req = urllib.request.Request(BASE + "/scores/all-holes/all-langs/all", headers=UA)
    with urllib.request.urlopen(req, timeout=600) as r:
        for raw in r:
            line = raw.decode("utf-8").strip().lstrip("[").rstrip(",]").strip()
            if line.startswith("{"):
                yield json.loads(line)


class Side:
    """Running-best (fewest bytes) over time for one side of one cell."""

    def __init__(self):
        self.subs = []

    def finish(self):
        self.subs.sort()
        self.days, self.best = [], []
        m = None
        for d, b in self.subs:
            if m is None or b < m:
                m = b
                if self.days and self.days[-1] == d:
                    self.best[-1] = m
                else:
                    self.days.append(d)
                    self.best.append(m)

    def at(self, day):
        i = bisect.bisect_right(self.days, day) - 1
        return self.best[i] if i >= 0 else None


def status(a, h):
    # 1 AI leads, 2 humans lead, 3 tied, 4 AI only, 5 humans only, 0 nothing
    if a is not None and h is not None:
        return 1 if a < h else 2 if a > h else 3
    if a is not None:
        return 4
    if h is not None:
        return 5
    return 0


def main():
    with open(os.path.join(HERE, "..", "ai_accounts.txt")) as f:
        ai = {l.strip() for l in f if l.strip() and not l.startswith("#")}

    holes = [h for h in get_json("/api/holes") if not h.get("experiment")]
    hole_info = {h["id"]: (h["name"], h["category"]) for h in holes}
    lang_name = {l["id"]: l["name"] for l in get_json("/api/langs")}

    cells, events, n = {}, {}, 0
    for e in stream_feed():
        n += 1
        if e.get("scoring") != "bytes" or e["hole"] not in hole_info:
            continue
        key = (e["hole"], e["lang"])
        c = cells.get(key)
        if c is None:
            c = cells[key] = (Side(), Side())
        day = dt.date.fromisoformat(e["submitted"][:10]).toordinal()
        (c[0] if e["login"] in ai else c[1]).subs.append((day, e["bytes"]))
        events.setdefault(key, []).append((e["submitted"][:19], e["bytes"], e["login"]))
    for a, h in cells.values():
        a.finish()
        h.finish()
    print(f"read {n:,} solutions, {len(cells):,} hole/lang cells", file=sys.stderr)

    today = dt.date.today()
    weeks = []
    d = START
    while d <= today:
        weeks.append(d)
        d += dt.timedelta(days=7)
    if weeks[-1] != today:
        weeks.append(today)
    months = weeks[::4] if (len(weeks) - 1) % 4 == 0 else weeks[::4] + [weeks[-1]]

    weekly = [[0] * 5 for _ in weeks]
    hole_m = {}  # (hole, i) -> [ai, human, tie]
    lang_m = {}  # (lang, i) -> [s1..s5]
    cells_rows = []
    for (hole, lang), (A, H) in cells.items():
        for i, w in enumerate(weeks):
            s = status(A.at(w.toordinal()), H.at(w.toordinal()))
            if s:
                weekly[i][s - 1] += 1
        for i, w in enumerate(months):
            s = status(A.at(w.toordinal()), H.at(w.toordinal()))
            if 1 <= s <= 3:
                hole_m.setdefault((hole, i), [0, 0, 0])[s - 1] += 1
            if s:
                lang_m.setdefault((lang, i), [0] * 5)[s - 1] += 1
        s = status(A.at(10**9), H.at(10**9))
        if s:
            name, cat = hole_info[hole]
            cells_rows.append({"hole": name, "category": cat, "lang": lang_name.get(lang, lang),
                               "status": ["", "AI leads", "Humans lead", "Tied", "AI only", "Humans only"][s]})

    weekly_rows = [{"week": w.isoformat(), "ai_leads": c[0], "human_leads": c[1], "tied": c[2],
                    "ai_only": c[3], "human_only": c[4]} for w, c in zip(weeks, weekly)]

    hole_rows = []
    for h in holes:
        for i, w in enumerate(months):
            c = hole_m.get((h["id"], i))
            if not c:
                continue
            t = sum(c)
            a, hu = round(100 * c[0] / t), round(100 * c[1] / t)
            hole_rows.append({"hole": h["name"], "category": h["category"], "date": w.isoformat(),
                              "ai_lead_pct": a, "human_lead_pct": hu, "tied_pct": max(0, 100 - a - hu)})

    lang_rows = []
    for lang in sorted({k[0] for k in lang_m}):
        for i, w in enumerate(months):
            c = lang_m.get((lang, i))
            if not c:
                continue
            t = sum(c)
            a, ti = round(100 * (c[0] + c[3]) / t), round(100 * c[2] / t)
            lang_rows.append({"lang": lang_name.get(lang, lang), "date": w.isoformat(), "ai_held_pct": a,
                              "tied_pct": ti, "human_held_pct": max(0, 100 - a - ti), "holes_solved": t})

    # Most recent record changes: a new shortest solution, a tie of the record, or a first solve.
    side = lambda login: "AI" if login in ai else "Human"
    recent = []
    cutoff = (today - dt.timedelta(days=RECENT_DAYS)).isoformat()
    for (hole, lang), subs in events.items():
        subs.sort()
        best, holder = None, None
        for ts, b, login in subs:
            if best is None or b < best:
                kind = "First solve" if best is None else "New record"
                prev, prev_holder = best, holder
                best, holder = b, login
            elif b == best:
                kind, prev, prev_holder = "Tied record", best, holder
            else:
                continue
            if ts[:10] >= cutoff:
                name, cat = hole_info[hole]
                recent.append({"when": ts + "Z", "hole": name, "lang": lang_name.get(lang, lang), "golfer": login,
                               "side": side(login), "kind": kind, "bytes": b,
                               "prev_bytes": prev, "prev_holder": prev_holder,
                               "prev_side": side(prev_holder) if prev_holder else None,
                               "change": None if prev is None else b - prev})
    recent.sort(key=lambda r: r["when"], reverse=True)
    recent = recent[:RECENT_MAX]

    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    out = {
        "weekly": weekly_rows,
        "cells": cells_rows,
        "hole_month": hole_rows,
        "lang_month": lang_rows,
        "recent": recent,
        "meta": [{"updated_at": now, "solutions": n, "ai_accounts": len(ai)}],
    }
    for name, rows in out.items():
        with open(os.path.join(OUT, name + ".json"), "w") as f:
            json.dump({"rows": rows}, f, ensure_ascii=False, separators=(",", ":"))
    last = weekly_rows[-1]
    print(f"done: AI leads {last['ai_leads']}, humans {last['human_leads']}, tied {last['tied']}", file=sys.stderr)


if __name__ == "__main__":
    main()
