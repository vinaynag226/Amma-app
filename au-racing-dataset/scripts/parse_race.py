#!/usr/bin/env python3
"""
Parsers for Racenet form-guide/results markdown (as returned by nimble_extract
in output_format="markdown").

Two entry points:
  parse_results_page(markdown_text, url) -> race dict + list of runner dicts
  parse_gear_changes(markdown_text) -> {race_number: {horse_name: gear_change_text}}

Designed to be reused unchanged by every scraping subagent so the whole
dataset comes out of one parsing implementation.
"""
import re
import sys
import json
from datetime import datetime


MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}


def _clean(s):
    return re.sub(r"\s+", " ", s).strip() if s else s


def parse_meeting_date_from_url(url):
    """ascot-20250329 -> 2025-03-29"""
    m = re.search(r"-(\d{8})(?:-bt)?/", url + "/")
    if not m:
        return None
    d = m.group(1)
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"


TRACK_ALIASES = {
    "belmont": "Belmont",
    "belmont park": "Belmont",
    "pinjarra": "Pinjarra",
    "pinjarra scarp": "Pinjarra",
    "pinjarra scarpside": "Pinjarra",
    "pinjarra park": "Pinjarra",
    "ascot": "Ascot",
    "bunbury": "Bunbury",
    "northam": "Northam",
    "geraldton": "Geraldton",
    "york": "York",
    "narrogin": "Narrogin",
}


def parse_track_from_url(url):
    m = re.search(r"/(?:form-guide|results)/horse-racing/([a-z0-9-]+)-\d{8}", url)
    if not m:
        return None
    raw = m.group(1).replace("-", " ").title()
    return TRACK_ALIASES.get(raw.lower(), raw)


def parse_race_number_from_url(url):
    m = re.search(r"-race-(\d+)", url)
    return int(m.group(1)) if m else None


def parse_results_page(text, url=""):
    """Parse a racenet.com.au/results/horse-racing/{track}-{date}/{slug}-race-{n} page."""
    race = {
        "url": url,
        "track": parse_track_from_url(url),
        "date": parse_meeting_date_from_url(url),
        "race_number": parse_race_number_from_url(url),
    }

    # Track condition, e.g. "light rain Good 4"
    m = re.search(r"\n(?:!\[[^\]]*\]\([^)]*\)\s*)?([A-Za-z ]*?)(Good|Firm|Soft|Heavy)\s*(\d)\s*\n", text)
    if m:
        race["track_condition"] = f"{m.group(2)} {m.group(3)}"
        race["weather"] = _clean(m.group(1)) or None
    else:
        race["track_condition"] = None
        race["weather"] = None

    # Race header: "## R1 Peters Investments Hcp" then "1400m" then "Class: ..."
    m = re.search(r"##\s*R(\d+)\s+(.+?)\n+([\d,]+)m\n+Class:\s*(.+?)\n", text)
    if m:
        race["race_number"] = race["race_number"] or int(m.group(1))
        race["race_name"] = _clean(m.group(2))
        race["distance_m"] = int(m.group(3).replace(",", ""))
        race["class_raw"] = _clean(m.group(4))
    else:
        race["race_name"] = None
        race["distance_m"] = None
        race["class_raw"] = None

    # Prize money
    m = re.search(r"Prize:\s*\$([\d,]+)", text)
    race["prize_total"] = int(m.group(1).replace(",", "")) if m else None

    # Rail position / track info
    m = re.search(r"Track Info:\s*(.+?)\n", text)
    race["track_info"] = _clean(m.group(1)) if m else None

    # Full date+time, e.g. "Saturday 29 March 2025 04:29AM"
    m = re.search(r"(\w+ \d{1,2} (?:%s) \d{4})\s+(\d{1,2}:\d{2}[AP]M)" % "|".join(MONTHS), text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%A %d %B %Y")
            race["date"] = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        race["race_time"] = m.group(2)

    m = re.search(r"Time:\s*([\d:.]+)\n", text)
    race["race_time_elapsed"] = m.group(1) if m else None

    m = re.search(r"Sectional Time:\s*([\d:.]+)\s*at\s*(\d+)m", text)
    if m:
        race["sectional_time"] = m.group(1)
        race["sectional_at_m"] = int(m.group(2))

    # ---- Runners: "Final Results" block ----
    runners = []
    results_block_match = re.search(r"###\s*Final Results\n(.*?)\nScratchings:", text, re.S)
    scratch_names = set()
    if results_block_match:
        block = results_block_match.group(1)
    else:
        # No scratchings line found (rare) - take to Exotics or end
        block = re.search(r"###\s*Final Results\n(.*?)(?:\nExotics|\Z)", text, re.S)
        block = block.group(1) if block else ""

    # Each runner starts with an image line + "Nth <margin>" then "#### [num\. Name](url)"
    runner_pattern = re.compile(
        r"!\[[^\]]*\]\([^)]*\)\s*(\d+)(?:st|nd|rd|th)\s*([\d.]*L|\\?-|\S*)\s*\n+"
        r"####\s*\[(\d+)\\?\.\s*([^\]]+)\]\(([^)]+)\)\n+"
        r"\((\d+)\)\n+"
        r"(\d+)yo\n+"
        r"\(([A-Z])\)\n+"
        r"\[T:\s*([^\]]+)\]\([^)]+\)\s*\[J:\s*([^\]]+)\]\([^)]+\)\n+"
        r"\(([\d.]+kg(?:\s*cd\s*[\d.]+kg)?)\)\n+"
        r"(.+?)\n+"  # pedigree line, ignored
        r"(?:\[Form\]\([^)]+\)\n+)?"
        r"800\n+(\S+)\n+400\n+(\S+)\n+"
        r"Margin\n+([\d.]*L|\\?-)\n+"
        r"W\n+P\n+SP\n+([\d.]+|\\?-)\n+([\d.]+|\\?-)\n"
    )

    for m in runner_pattern.finditer(block):
        (finish_pos, margin_hdr, num, name, horse_url, barrier, age, sex,
         trainer, jockey, weight_raw, pedigree, pos800, pos400, margin2,
         win_sp, place_sp) = m.groups()

        weight_kg = None
        claim_kg = None
        wm = re.match(r"([\d.]+)kg(?:\s*cd\s*([\d.]+)kg)?", weight_raw)
        if wm:
            weight_kg = float(wm.group(1))
            if wm.group(2):
                claim_kg = round(weight_kg - float(wm.group(2)), 1)

        DASHES = ("", "-", "\\-")
        margin = margin2 if margin2 not in DASHES else (margin_hdr if margin_hdr not in DASHES else None)

        runners.append({
            "finish_position": int(finish_pos),
            "runner_number": int(num),
            "horse_name": _clean(name),
            "horse_url": horse_url,
            "barrier": int(barrier),
            "age": int(age),
            "sex": sex,
            "trainer": _clean(trainer),
            "jockey": _clean(jockey),
            "weight_kg": weight_kg,
            "claim_kg": claim_kg,
            "apprentice": claim_kg is not None and claim_kg > 0,
            "margin": margin,
            "sectional_800_pos": pos800,
            "sectional_400_pos": pos400,
            "win_sp": None if win_sp in ("-", "\\-") else float(win_sp),
            "place_sp": None if place_sp in ("-", "\\-") else float(place_sp),
            "scratched": False,
        })

    # Scratchings
    m = re.search(r"Scratchings:\s*(.+?)(?:\n\n|\nExotics|\Z)", text, re.S)
    if m:
        for part in m.group(1).split(","):
            sm = re.search(r"(\d+)\\?\.\s*(.+)", part.strip())
            if sm:
                scratch_names.add((int(sm.group(1)), _clean(sm.group(2))))

    for snum, sname in scratch_names:
        runners.append({
            "finish_position": None,
            "runner_number": snum,
            "horse_name": sname,
            "horse_url": None,
            "barrier": None,
            "age": None,
            "sex": None,
            "trainer": None,
            "jockey": None,
            "weight_kg": None,
            "claim_kg": None,
            "apprentice": None,
            "margin": None,
            "sectional_800_pos": None,
            "sectional_400_pos": None,
            "win_sp": None,
            "place_sp": None,
            "scratched": True,
        })

    race["field_size"] = len(runners)
    return race, runners


def parse_race_slugs(text):
    """From an /overview or /all-races page, extract [(race_number, race_slug), ...]
    by reading the meeting's "[R 1](.../{slug}/overview)" sidebar links.
    """
    out = []
    seen = set()
    for m in re.finditer(r"\[R\s*(\d+)\]\(https?://[^)]+?/([a-z0-9'-]+-race-\d+)/overview\)", text):
        rno = int(m.group(1))
        if rno in seen:
            continue
        seen.add(rno)
        out.append((rno, m.group(2)))
    return out


def parse_gear_changes(text):
    """Parse the meeting-wide gear-changes block from an /overview page.
    Returns {race_number: {horse_name: "Blinkers first time, ..."}}
    Stops at the first jockey-index name to avoid bleeding into that section.
    """
    out = {}
    block_match = re.search(r"Gear Changes & Indexes.*?Trainers\n(.*)", text, re.S)
    if not block_match:
        return out
    block = block_match.group(1)

    # cut off the block once jockey/trainer indexes start: those begin with a
    # line "<Firstname Lastname>" immediately followed by "R<n>" then "**H:**"
    end_match = re.search(r"\n[A-Z][a-zA-Z .&'-]+\n+R\d+\n+\*\*H:\*\*", block)
    if end_match:
        block = block[:end_match.start()]

    race_sections = re.split(r"\nR(\d+)\s+(.+?)\n", "\n" + block)
    # race_sections[0] is preamble; then triples of (race_num, race_name, body)
    for i in range(1, len(race_sections) - 2, 3):
        rno = int(race_sections[i])
        body = race_sections[i + 2]
        if "No Gear changes" in body:
            out[rno] = {}
            continue
        horse_changes = {}
        for hm in re.finditer(r"(\d+)\\?\.\s*(.+?)\n+(.+?)(?=\n\d+\\?\.|\Z)", body, re.S):
            hname = _clean(hm.group(2))
            change = _clean(hm.group(3))
            horse_changes[hname] = change
        out[rno] = horse_changes
    return out


if __name__ == "__main__":
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "results"
    with open(path) as f:
        text = f.read()
    if mode == "results":
        url = sys.argv[3] if len(sys.argv) > 3 else ""
        race, runners = parse_results_page(text, url)
        print(json.dumps({"race": race, "runners": runners}, indent=2))
    elif mode == "gear":
        print(json.dumps(parse_gear_changes(text), indent=2))
    elif mode == "slugs":
        print(json.dumps(parse_race_slugs(text)))
