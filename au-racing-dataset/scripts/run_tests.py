#!/usr/bin/env python3
"""
Run the three requested statistical tests against au_racing.db and print a
JSON report: year-by-year win%/place% per group, sample sizes, and a
zero-reversal check (does the effect direction hold in every year?).
"""
import argparse
import json
import sqlite3


def year_breakdown(conn, base_sql, group_col, params=()):
    """base_sql must select: year, group_val, win, placed for each qualifying runner row."""
    rows = conn.execute(base_sql, params).fetchall()
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "wins": 0, "places": 0})
    for year, group_val, win, placed in rows:
        key = (year, group_val)
        agg[key]["n"] += 1
        agg[key]["wins"] += win or 0
        agg[key]["places"] += placed or 0

    years = sorted(set(y for (y, g) in agg))
    groups = sorted(set(g for (y, g) in agg))
    out = {"years": {}, "overall": {}}
    for y in years:
        out["years"][y] = {}
        for g in groups:
            d = agg.get((y, g), {"n": 0, "wins": 0, "places": 0})
            n = d["n"]
            out["years"][y][g] = {
                "n": n,
                "win_pct": round(100 * d["wins"] / n, 2) if n else None,
                "place_pct": round(100 * d["places"] / n, 2) if n else None,
            }
    for g in groups:
        n = sum(agg[(y, g)]["n"] for y in years if (y, g) in agg)
        wins = sum(agg[(y, g)]["wins"] for y in years if (y, g) in agg)
        places = sum(agg[(y, g)]["places"] for y in years if (y, g) in agg)
        out["overall"][g] = {
            "n": n,
            "win_pct": round(100 * wins / n, 2) if n else None,
            "place_pct": round(100 * places / n, 2) if n else None,
        }
    return out


def check_reversals(breakdown, favored_group, other_group, metric="win_pct"):
    """Return list of years where other_group beat favored_group on `metric` (a reversal)."""
    reversals = []
    for y, g in breakdown["years"].items():
        a = g.get(favored_group, {}).get(metric)
        b = g.get(other_group, {}).get(metric)
        if a is not None and b is not None and b > a:
            reversals.append(y)
    return sorted(reversals)


def test_class_movement(conn):
    sql = """
        SELECT CAST(strftime('%Y', ra.date) AS INTEGER) AS year,
               CASE WHEN r.class_movement = 'lower' THEN 'class_drop' ELSE 'no_drop' END AS grp,
               r.win, r.placed
        FROM runners r JOIN races ra ON r.race_id = ra.race_id
        WHERE r.scratched = 0 AND r.class_movement IN ('lower', 'equal', 'higher')
    """
    bd = year_breakdown(conn, sql, "grp")
    bd["reversals_win"] = check_reversals(bd, "class_drop", "no_drop", "win_pct")
    bd["reversals_place"] = check_reversals(bd, "class_drop", "no_drop", "place_pct")
    return bd


def test_apprentice(conn):
    sql = """
        SELECT CAST(strftime('%Y', ra.date) AS INTEGER) AS year,
               CASE WHEN r.apprentice = 1 THEN 'apprentice' ELSE 'senior' END AS grp,
               r.win, r.placed
        FROM runners r JOIN races ra ON r.race_id = ra.race_id
        WHERE r.scratched = 0 AND r.apprentice IS NOT NULL AND ra.distance_m >= 1600
    """
    bd = year_breakdown(conn, sql, "grp")
    bd["reversals_win"] = check_reversals(bd, "apprentice", "senior", "win_pct")
    bd["reversals_place"] = check_reversals(bd, "apprentice", "senior", "place_pct")
    return bd


def test_simon_miller_blinkers(conn):
    sql = """
        SELECT CAST(strftime('%Y', ra.date) AS INTEGER) AS year,
               CASE WHEN r.first_time_gear LIKE '%Blinkers first time%' THEN 'first_time_blinkers'
                    ELSE 'no_first_time_blinkers' END AS grp,
               r.win, r.placed
        FROM runners r JOIN races ra ON r.race_id = ra.race_id
        WHERE r.scratched = 0 AND r.trainer LIKE 'Simon%Miller' AND r.trainer NOT LIKE 'Stephen%'
    """
    bd = year_breakdown(conn, sql, "grp")
    bd["reversals_win"] = check_reversals(bd, "first_time_blinkers", "no_first_time_blinkers", "win_pct")
    bd["reversals_place"] = check_reversals(bd, "first_time_blinkers", "no_first_time_blinkers", "place_pct")
    return bd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="au_racing.db")
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)

    report = {
        "class_movement": test_class_movement(conn),
        "apprentice_1600plus_wa": test_apprentice(conn),
        "simon_miller_blinkers": test_simon_miller_blinkers(conn),
    }
    print(json.dumps(report, indent=2, default=str))
