#!/usr/bin/env python3
"""
Heuristic ordinal ranking of Australian thoroughbred race "Class:" text so
class movement (higher / lower / equal) can be inferred between a runner's
consecutive starts.

This is necessarily approximate: benchmark/restricted grading is
rating-relative, not a strict national ladder, and race-to-race comparisons
of e.g. "BM66" at two different tracks are not perfectly equivalent. Treat
the output as a heuristic signal, not a certified classification -- this
limitation is called out in the dataset's data-quality notes.

Ladder (low -> high):
  0   Maiden
  10  Restricted (Rs / "0 metro wins" etc.)
  20  Class 1
  25  Class 2
  30  Class 3
  35  Class 4
  40  Class 5
  45  Class 6+
  Benchmark/Handicap: scored by benchmark number directly (e.g. BM66 -> 66)
    when present, which overlaps/interleaves with the class numbers above by
    design (a BM66 is roughly open/mid-grade city company).
  200 Listed
  300 Group 3
  400 Group 2
  500 Group 1
"""
import re


def class_score(class_raw):
    """Return (score, tags) for a race's raw Class: text, or (None, []) if unparseable."""
    if not class_raw:
        return None, []
    t = class_raw.lower()
    tags = []

    if "group 1" in t or re.search(r"\bg1\b", t):
        return 500, ["group1"]
    if "group 2" in t or re.search(r"\bg2\b", t):
        return 400, ["group2"]
    if "group 3" in t or re.search(r"\bg3\b", t):
        return 300, ["group3"]
    if "listed" in t:
        return 200, ["listed"]

    m = re.search(r"\bbm\s*-?\s*(\d{2,3})\b", t) or re.search(r"benchmark\s*(\d{2,3})", t)
    if m:
        return float(m.group(1)), ["benchmark"]

    if re.search(r"\bmaiden\b", t):
        return 0, ["maiden"]

    m = re.search(r"\bclass\s*(\d)\b", t)
    if m:
        return 15 + 5 * int(m.group(1)), ["class" + m.group(1)]

    if re.search(r"\brs\s*\d*[a-z]*\b", t) or "restricted" in t:
        return 10, ["restricted"]

    if "open" in t and "handicap" in t:
        return 50, ["open_handicap"]
    if "welter" in t:
        return 55, ["welter"]
    if "handicap" in t or "hcp" in t:
        return 45, ["handicap"]

    return None, []


def compare_class(prev_raw, curr_raw):
    """Return 'higher' | 'lower' | 'equal' | 'unknown' for curr relative to prev."""
    prev_score, _ = class_score(prev_raw)
    curr_score, _ = class_score(curr_raw)
    if prev_score is None or curr_score is None:
        return "unknown"
    if curr_score > prev_score:
        return "higher"
    if curr_score < prev_score:
        return "lower"
    return "equal"


if __name__ == "__main__":
    import sys
    tests = [
        "3yo, open, Handicap",
        "Maiden",
        "BM66",
        "Bm66+",
        "Rs1mw",
        "Rs0ly",
        "Listed",
        "Group 1",
        "Class 1",
        "Class 3, Handicap",
    ]
    for t in tests:
        print(f"{t!r:30s} -> {class_score(t)}")
