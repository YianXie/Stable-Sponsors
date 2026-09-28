"""Generate a fake two-cycle Interim dataset with the real files' exact layout.

    python tools/make_synthetic.py --out ~/interim-synthetic

Writes <out>/raw/2026/... and <out>/raw/2027/... with the same file names,
sheet names and headers as the office's files (including the trailing spaces
in the 2026 international form and the trip-code column in the 2026 offerings,
filled only for courses that ran), plus <out>/truth.json, which the end-to-end
test uses to score every proposed link. All people and courses are invented.

Deliberately hard cases:
  - a nickname on the form ("Marty") vs the placement sheet ("Martin")
  - two teachers whose emails share a key (dkim@, dkim2@), one new in 2027
  - a middle initial and a "Last, First" placement entry for the same person
  - a double surname dropped to one surname on the placement sheet
  - an apostrophe surname, and a surname-first name with a non-standard email
  - placement course names that differ from the offerings names (suffix,
    shortened, typo, '&' vs 'and', and one completely rephrased)
  - a course whose trip code changes between cycles, held by a repeater
  - a prior course given by name instead of code
  - courses with a third sponsor on an extra row (blank or repeated code)
  - Singapore course SING-9 missing from the 2026 placement sheet while
    teachers still rank it on the Singapore form
  - a duplicate form submission, an 'N/A' preference, and free text that
    names a colleague
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from idmap import match_score, norm_course  # noqa: E402

DOMAIN = "sas.edu.sg"
PREF_WORDS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh"]

DEST = [
    ("Nepal", "Kathmandu", "NPL"), ("Bhutan", "Paro", "BTN"), ("Cambodia", "Siem Reap", "KHM"),
    ("Laos", "Luang Prabang", "LAO"), ("Vietnam", "Hanoi", "VNM"), ("Thailand", "Chiang Mai", "THA"),
    ("Malaysia", "Kuching", "MYS"), ("Indonesia", "Yogyakarta", "IDN"), ("Philippines", "Cebu", "PHL"),
    ("Japan", "Kyoto", "JPN"), ("South Korea", "Seoul", "KOR"), ("Mongolia", "Ulaanbaatar", "MNG"),
    ("Taiwan", "Taipei", "TWN"), ("India", "Jaipur", "IND"), ("Sri Lanka", "Kandy", "LKA"),
    ("Maldives", "Male", "MDV"), ("Australia", "Cairns", "AUS"), ("New Zealand", "Queenstown", "NZL"),
    ("Fiji", "Nadi", "FJI"), ("Palau", "Koror", "PLW"), ("Tanzania", "Arusha", "TZA"),
    ("Kenya", "Nairobi", "KEN"), ("Rwanda", "Kigali", "RWA"), ("Uganda", "Entebbe", "UGA"),
    ("South Africa", "Cape Town", "ZAF"), ("Namibia", "Windhoek", "NAM"), ("Botswana", "Maun", "BWA"),
    ("Morocco", "Marrakech", "MAR"), ("Egypt", "Luxor", "EGY"), ("Oman", "Muscat", "OMN"),
    ("Turkey", "Istanbul", "TUR"), ("Greece", "Athens", "GRC"), ("Italy", "Siena", "ITA"),
    ("Spain", "Seville", "ESP"), ("Portugal", "Lisbon", "PRT"), ("France", "Lyon", "FRA"),
    ("Iceland", "Reykjavik", "ISL"), ("Norway", "Tromso", "NOR"), ("Finland", "Rovaniemi", "FIN"),
    ("Scotland", "Edinburgh", "SCO"), ("Ireland", "Galway", "IRL"), ("Netherlands", "Amsterdam", "NLD"),
    ("Germany", "Berlin", "DEU"), ("Czechia", "Prague", "CZE"), ("Poland", "Krakow", "POL"),
    ("Croatia", "Dubrovnik", "HRV"), ("Uzbekistan", "Samarkand", "UZB"), ("Kyrgyzstan", "Bishkek", "KGZ"),
    ("Peru", "Cusco", "PER"), ("Ecuador", "Quito", "ECU"), ("Costa Rica", "San Jose", "CRI"),
    ("Belize", "Belize City", "BLZ"), ("Mexico", "Oaxaca", "MEX"), ("Chile", "Santiago", "CHL"),
    ("Argentina", "Mendoza", "ARG"), ("Canada", "Banff", "CAN"), ("Hawaii", "Hilo", "HAW"),
    ("Alaska", "Anchorage", "AKA"), ("Madagascar", "Antananarivo", "MDG"), ("Ghana", "Accra", "GHA"),
]
THEMES = [
    ("Mountain Trek", "TRK"), ("Service Learning", "SVC"), ("Marine Conservation", "MCN"),
    ("Wildlife Safari", "SAF"), ("Culture & Cuisine", "CUL"), ("Arts & Heritage", "ART"),
    ("Rainforest Ecology", "ECO"), ("Scuba Discovery", "DIV"), ("Community Build", "BLD"),
    ("History Walk", "HIS"), ("Photography Journey", "PHO"), ("Language Immersion", "LNG"),
    ("Cycling Tour", "CYC"), ("Kayak Adventure", "KAY"), ("Science & Astronomy", "SCI"),
]
FT_2026_INTL = ["Any important comments or priorities regarding your co-sponsor?",
                "Please share relevant and notable experience, certifications, and skills "
                "connected to your preferred courses.",
                "Any final questions or comments?"]
FT_2026_SG = FT_2026_INTL[1:]
FT_2027_INTL = ["How can you uniquely enhance student learning or safety on a specific course?",
                "Any notable priorities you would like to share?",
                "Any final questions or comments?"]
FT_2027_SG = [FT_2027_INTL[0], "Any additional comments?"]
MISSING_2026 = "SING-9"      # absent from the 2026 placement sheet, as in the real data
SG_ALL = [
    ("Singapore Heritage Trails", "SING-1"), ("Singapore Urban Farming", "SING-2"),
    ("Singapore Hawker Cuisine", "SING-3"), ("Singapore Coastal Cleanup", "SING-4"),
    ("Singapore Mangrove Ecology", "SING-5"), ("Singapore Street Art", "SING-6"),
    ("Singapore Makers Lab", "SING-7"), ("Singapore Wellness & Yoga", "SING-8"),
    ("Singapore Film Studio", "SING-9"), ("Singapore Community Service", "SING-10"),
    ("Singapore Island Kayaking", "SING-11"), ("Singapore Botanic Sketching", "SING-12"),
]
FIRST = ["Aaron", "Abigail", "Adrian", "Aisha", "Alan", "Alicia", "Amir", "Andrea", "Anika", "Arjun",
         "Beatrice", "Brandon", "Bridget", "Caleb", "Camila", "Carlos", "Chloe", "Colin", "Diana",
         "Dmitri", "Eduardo", "Elena", "Elise", "Emeka", "Erin", "Farah", "Felix", "Fiona", "Gavin",
         "Hana", "Hassan", "Helena", "Hiroshi", "Imogen", "Irene", "Isaac", "Jasmine", "Javier",
         "Joanna", "Jonas", "Julia", "Kenji", "Keisha", "Lars", "Laura", "Leila", "Lucas", "Lydia",
         "Malik", "Marcus", "Mira", "Nadia", "Naveen", "Nora", "Omar", "Oscar", "Paula", "Priya",
         "Rafael", "Rania", "Ravi", "Rosa", "Ruth", "Sakura", "Santiago", "Selena", "Shira", "Simone",
         "Tariq", "Tessa", "Tobias", "Valeria", "Wendy", "Xavier", "Yara", "Yusuf", "Zara"]
LAST = ["Abbott", "Adeyemi", "Alvarez", "Andersson", "Baker", "Banerjee", "Barros", "Bennett",
        "Brennan", "Castillo", "Chandra", "Choi", "Coleman", "Dang", "Delgado", "Dubois", "Eriksen",
        "Ferreira", "Fischer", "Fong", "Gallagher", "Gupta", "Haddad", "Hartley", "Hoffmann",
        "Ibrahim", "Iyer", "Jansen", "Johansson", "Kapoor", "Kaur", "Keller", "Kowalski", "Kumar",
        "Lambert", "Larsen", "Lopes", "Mahmoud", "Martens", "Mendez", "Moreau", "Murphy", "Nakamura",
        "Navarro", "Nguyen", "Novak", "Okafor", "Olsen", "Ortiz", "Patel", "Pereira", "Quinn",
        "Ramos", "Reyes", "Richter", "Rossi", "Sato", "Schmidt", "Sharma", "Silva", "Singh",
        "Suzuki", "Takahashi", "Torres", "Tran", "Vargas", "Vogel", "Wagner", "Walsh", "Weber",
        "Yamamoto", "Yilmaz", "Zhang"]


def write_xlsx(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)


def email_for(first, last, taken):
    base = "".join(ch for ch in (first[0] + last).lower() if ch.isalpha())
    local, n = base, 1
    while local in taken:
        n += 1
        local = f"{base}{n}"
    taken.add(local)
    return f"{local}@{DOMAIN}"


def generate(out: Path, seed: int = 7) -> dict:
    rng = random.Random(seed)
    raw = out / "raw"

    # ------------------------------------------------------------ people
    people = {}                      # pid -> dict(first, last, email, names{context: display})
    taken = set()

    def add_person(first, last, email=None, display=None):
        pid = f"P{len(people) + 1:03d}"
        e = email or email_for(first, last, taken)
        if email:
            taken.add(email.split("@")[0])
        people[pid] = dict(first=first, last=last, email=e,
                           display=display or f"{first} {last}", variants={})
        return pid

    sp = {
        "martin": add_person("Martin", "Williams"),
        "daniel": add_person("Daniel", "Kim"),
        "maria": add_person("Maria", "Garcia-Lopez", email=f"mgarcialopez@{DOMAIN}"),
        "grace": add_person("Grace", "Tan"),
        "david": add_person("David", "Kim"),                 # gets dkim2@
        "sean": add_person("Sean", "O'Brien", email=f"sobrien@{DOMAIN}"),
        "twm": add_person("Tan Wei", "Ming", email=f"weiming.tan@{DOMAIN}", display="Tan Wei Ming"),
        "dana": add_person("Dana", "Kim"),                   # 2026 repeater who left; no email in data
        "sam": add_person("Sam", "Lee"),                     # slee@  } both new in 2027:
        "samantha": add_person("Samantha", "Lee"),           # slee2@ } genuinely ambiguous
        "qiang": add_person("Qiang", "Zhou"),                # submits round 1, is not placed
        "quinn": add_person("Quinn", "Zhou"),                # placed without responding (qzhou2@ unseen)
    }
    people[sp["martin"]]["variants"] = {"form2026": "Marty Williams"}
    people[sp["grace"]]["variants"] = {"place2026": "Grace L. Tan", "place2027": "Tan, Grace"}
    people[sp["maria"]]["variants"] = {"place2027": "Maria Garcia"}

    def clean_against_all(first, last):
        e = f"{(first[0] + last).lower()}@{DOMAIN}"
        name = f"{first} {last}"
        for p in people.values():               # no accidental key collisions; fuzzy
            if match_score(e, p["display"])[1] >= 0.72 or \
                    match_score(p["email"], name)[1] >= 0.72:     # near-misses are kept
                return False
        return True

    combos = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(combos)
    for f, l in combos:
        if len(people) >= 170:
            break
        if clean_against_all(f, l):
            add_person(f, l)
    pids = list(people)
    special_new = [sp["david"], sp["sean"], sp["twm"], sp["sam"], sp["samantha"],
                   sp["qiang"], sp["quinn"]]
    special_cont = {sp["martin"], sp["daniel"], sp["maria"], sp["grace"]}
    others = [p for p in pids if p not in set(special_new) | special_cont | {sp["dana"]}]
    rng.shuffle(others)
    new27 = special_new + others[:13]
    leavers = [sp["dana"]] + others[13:32]
    cont = list(special_cont) + others[32:]
    roster = {"2026": cont + leavers, "2027": cont + new27}

    def shown(pid, ctx):
        return people[pid]["variants"].get(ctx, people[pid]["display"])

    # ------------------------------------------------------------ courses
    dests = DEST[:]
    rng.shuffle(dests)
    universe = []
    for (country, city, iso), (theme, ab) in zip(dests, [rng.choice(THEMES) for _ in dests]):
        universe.append(dict(name=f"{country} {theme}", country=country, city=city,
                             code=f"{iso}-{ab}", theme=theme))
    offered = {"2026": universe[:52], "2027": universe[6:60]}

    truth = {"persons": {}, "courses": {}, "aliases": {}, "placements": {}, "repeaters": {},
             "expected_checks": {}, "prefs": []}
    for pid, p in people.items():
        names = {p["display"], *p["variants"].values()}
        truth["persons"][pid] = {"emails": [p["email"]], "names": sorted(names)}

    placed_prev = {}
    renumbered = None
    for cyc in ("2026", "2027"):
        offer = offered[cyc]
        SG = SG_ALL if cyc == "2026" else SG_ALL[:11]
        members = roster[cyc]
        code_of = {c["name"]: c["code"] for c in offer}

        # repeaters (known only in 2027)
        rep = {}
        if cyc == "2027":
            cands = [p for p in cont if p in placed_prev and placed_prev[p][0] in code_of.values()]
            rng.shuffle(cands)
            rep = {p: placed_prev[p][0] for p in cands[:35]}
            # one repeated course is renumbered in 2027
            ren_code = sorted(set(rep.values()))[0]
            renumbered = ren_code
            new_code = ren_code.split("-")[0] + "-X" + ren_code.split("-")[1][:2]
            for c in offer:
                if c["code"] == ren_code:
                    c["code27"] = new_code
            rep = {p: (new_code if c == ren_code else c) for p, c in rep.items()}
        else:
            pool = [p for p in members if p not in special_cont and p != sp["dana"]]
            rng.shuffle(pool)
            rep = {p: None for p in [sp["dana"]] + pool[:29]}   # 2026 repeaters: no file

        def code27(c):
            return c.get("code27", c["code"]) if cyc == "2027" else c["code"]

        rep_courses = {c for c in rep.values() if c}
        nr_pool = [c for c in offer if code27(c) not in rep_courses]
        rng.shuffle(nr_pool)
        not_run = {c["name"] for c in nr_pool[:(5 if cyc == "2026" else 4)]}
        ran = [c for c in offer if c["name"] not in not_run]

        # placement-name variants on ran courses without repeaters
        var_pool = [c for c in ran if code27(c) not in rep_courses]
        rng.shuffle(var_pool)
        pname = {c["name"]: c["name"] for c in ran}
        kinds = ["suffix", "short", "typo", "geo"] + (["amp"] if cyc == "2027" else [])
        amp_pool = [c for c in var_pool if "&" in c["name"]]
        for kind in kinds:
            if kind == "amp":
                if not amp_pool:
                    continue
                c = amp_pool[0]
                pname[c["name"]] = c["name"].replace("&", "and")
                var_pool.remove(c)
                continue
            c = next(x for x in var_pool if "&" not in x["name"])
            var_pool.remove(c)
            if kind == "suffix":
                pname[c["name"]] = c["name"] + " (Service Week)"
            elif kind == "short":
                pname[c["name"]] = f"{c['country']} {c['theme'].split()[0]}"
            elif kind == "typo":
                w = c["theme"].split()[0]
                i = 2
                typo = w[:i] + w[i + 1] + w[i] + w[i + 2:]
                pname[c["name"]] = c["name"].replace(w, typo, 1)
            elif kind == "geo":
                pname[c["name"]] = f"{c['country']} Expedition {cyc}"

        # capacity
        cap = {}
        for c in ran:
            cap[code27(c)] = 2
        for s_name, s_code in SG:
            cap[s_code] = 2
        extra3 = rng.sample([code27(c) for c in ran], 26)
        for code in extra3:
            cap[code] = 3
        for code in rep_courses:
            cap[code] = max(cap[code], sum(1 for v in rep.values() if v == code))

        seats = {code: [] for code in cap}
        # place repeaters
        if cyc == "2026":
            intl_codes = [code27(c) for c in ran]
            for p in rep:
                opts = [c for c in intl_codes if len(seats[c]) < cap[c]]
                seats[rng.choice(opts)].append(p)
        else:
            for p, code in rep.items():
                seats[code].append(p)
        nonrep = [p for p in members if p not in rep]
        rng.shuffle(nonrep)
        must_place = [p for p in (sp["sam"], sp["samantha"], sp["david"], sp["quinn"]) if p in nonrep]
        never_place = [p for p in (sp["qiang"],) if p in nonrep]     # submits, is never placed
        nonrep = [p for p in nonrep if p not in must_place and p not in never_place]
        nonrep = nonrep[:26] + must_place + nonrep[26:] + never_place   # never in sg_sub either
        sg_sub = nonrep[:26]
        for p in sg_sub:
            opts = [code for _, code in SG if len(seats[code]) < cap[code]]
            if opts:
                seats[rng.choice(opts)].append(p)
        placed_now = {p for s in seats.values() for p in s}
        rest = [p for p in nonrep if p not in placed_now and p not in never_place]
        intl_codes = [code27(c) for c in ran]
        it = iter(rest)
        for code in intl_codes:                     # every running course gets two sponsors
            while len(seats[code]) < 2:
                p = next(it, None)
                if p is None:
                    break
                seats[code].append(p)
                placed_now.add(p)
        for p in rest:
            if p in placed_now:
                continue
            opts = [c for c in intl_codes if len(seats[c]) < cap[c]]
            if not opts:
                continue
            seats[rng.choice(opts)].append(p)
            placed_now.add(p)
        r2_people = {p for p in rest if p in placed_now and cyc == "2027" and rng.random() < 0.15}
        where = {p: code for code, ps in seats.items() for p in ps}

        # ---------------------------------------------------- files
        d = raw / cyc
        if cyc == "2026":      # 2026 offerings carry a trip code, but only for courses that ran
            write_xlsx(d / "00_course_offerings.xlsx",
                       ["Trip Code", "Course Name", "Arrival City", "Country"],
                       [["" if c["name"] in not_run else c["code"], c["name"], c["city"],
                         c["country"]] for c in offer])
        else:
            write_xlsx(d / "00_course_offerings.xlsx", ["Course Name", "Arrival City", "Country"],
                       [[c["name"], c["city"], c["country"]] for c in offer])

        name_by_code = {code27(c): c["name"] for c in offer}
        sg_names = [n for n, _ in SG]
        sg_code_name = {code: n for n, code in SG}
        colleague = rng.choice(LAST)
        ft_opts = ["Open water certified (PADI).", "First aid trained.", "", "", "",
                   f"Happy to co-lead with {colleague}.", "Prefer late February dates."]

        def intl_list(p, exclude=None, include=None, k=7):
            pool = [c["name"] for c in offer if c["name"] != exclude]
            picks = rng.sample(pool, k)
            if include and include not in picks:
                picks[rng.randrange(k)] = include
            return picks

        r1_rows, r2_rows, sg_rows = [], [], []
        alias_truth = {"offerings": {}, "intl": {}, "sg": {}, "prior": {}}
        for c in offer:
            alias_truth["offerings"][c["name"]] = code27(c) if c["name"] not in not_run \
                else "NR:" + norm_course(c["name"])

        def tkey(course_name):
            c = next(x for x in offer if x["name"] == course_name)
            return code27(c) if course_name not in not_run else "NR:" + norm_course(course_name)

        dup_done = na_done = False
        silent = {sp["quinn"]}
        quinn_course = name_by_code.get(where.get(sp["quinn"]))
        for p in nonrep:
            if p in silent:
                continue
            e = people[p]["email"]
            placed_code = where.get(p)
            placed_name = name_by_code.get(placed_code)
            typed = shown(p, f"form{cyc}")
            if cyc == "2026" and rng.random() < 0.1:
                typed = typed.lower()
            if cyc == "2027" and p in r2_people:
                picks = intl_list(p, exclude=placed_name)
            elif p == sp["qiang"]:
                picks = intl_list(p, exclude=quinn_course)    # so Quinn's course is off his list
            else:
                picks = intl_list(p, include=placed_name)
            for s in picks:
                alias_truth["intl"][s] = tkey(s)
            ft = [rng.choice(ft_opts) for _ in range(3)]
            if cyc == "2026":
                row = [e, typed, picks[0] + " ", *ft, *picks[1:]]
                r1_rows.append(row)
                truth["prefs"] += [[cyc, "intl_r1", p, i, tkey(s)] for i, s in enumerate(picks, 1)]
            else:
                if not na_done:
                    picks = picks[:6] + ["N/A"]
                    na_done = True
                if not dup_done:
                    early = intl_list(p)
                    r1_rows.append([e, early[0], "", "", "", *early[1:]])
                    for s in early:
                        alias_truth["intl"][s] = tkey(s)
                    dup_done = True
                r1_rows.append([e, picks[0], *ft, *picks[1:]])
                truth["prefs"] += [[cyc, "intl_r1", p, i, tkey(s)]
                                   for i, s in enumerate(picks, 1) if s != "N/A"]
                if p in r2_people:
                    remaining = [c["name"] for c in offer if c["name"] not in picks
                                 and c["name"] != placed_name]
                    r2 = rng.sample(remaining, 2)
                    r2.insert(rng.randrange(3), placed_name)
                    r2_rows.append([e, *r2])
                    truth["prefs"] += [[cyc, "intl_r2", p, i, tkey(s)] for i, s in enumerate(r2, 1)]
                    for s in r2:
                        alias_truth["intl"][s] = tkey(s)
            if p in sg_sub:
                inc = sg_code_name.get(placed_code)
                sp_ = rng.sample(sg_names, 5)
                if inc and inc not in sp_:
                    sp_[rng.randrange(5)] = inc
                shown_sg = [s.replace("&", "and") if (s.endswith("Yoga") and rng.random() < 0.5) else s
                            for s in sp_]
                for s, s0 in zip(shown_sg, sp_):
                    alias_truth["sg"][s] = dict(SG)[s0]
                truth["prefs"] += [[cyc, "sg", p, i, dict(SG)[s0]] for i, s0 in enumerate(sp_, 1)]
                ft2 = [rng.choice(ft_opts) for _ in range(2)]
                if cyc == "2026":
                    sg_rows.append([e, typed, *shown_sg, *ft2])
                else:
                    sg_rows.append([e, *shown_sg, *ft2])

        if cyc == "2026":
            write_xlsx(d / "01_international_selections.xlsx",
                       ["Email Address", "Name (First & Last)", "First Preference ",
                        *FT_2026_INTL]
                       + [f"{w} Preference " for w in PREF_WORDS[1:]], r1_rows)
            write_xlsx(d / "02_singapore_selections.xlsx",
                       ["Email Address", "Name (First & Last)"]
                       + [f"{w} Preference" for w in PREF_WORDS[:5]]
                       + FT_2026_SG, sg_rows)
            place_file = "03_final_placements.xlsx"
        else:
            rep_rows = []
            by_name_done = False
            for p, code in rep.items():
                prior = code
                if not by_name_done and code != renumbered and not code.split("-")[1].startswith("X"):
                    prior = name_by_code[code]
                    by_name_done = True
                alias_truth["prior"][prior] = code
                rep_rows.append([people[p]["email"], prior])
            write_xlsx(d / "01_repeating_or_not.xlsx", ["Email Address", "Prior Course"], rep_rows)
            write_xlsx(d / "02_international_selections_round1.xlsx",
                       ["Email Address", "First Preference", *FT_2027_INTL]
                       + [f"{w} Preference" for w in PREF_WORDS[1:]],
                       r1_rows)
            write_xlsx(d / "03_international_selections_round2.xlsx",
                       ["Email Address"] + [f"{w} Preference" for w in PREF_WORDS[:3]], r2_rows)
            write_xlsx(d / "04_singapore_selections.xlsx",
                       ["Email Address"] + [f"{w} Preference" for w in PREF_WORDS[:5]]
                       + FT_2027_SG, sg_rows)
            place_file = "05_final_placements.xlsx"
            truth["repeaters"][cyc] = rep

        rows, ptruth, blank_style = [], [], True
        order = [code27(c) for c in ran] + [code for _, code in SG]
        for code in order:
            ps = seats[code]
            if not ps or (cyc == "2026" and code == MISSING_2026):
                continue            # SING-9's sponsors simply do not appear on the 2026 sheet
            nm = pname.get(name_by_code.get(code), sg_code_name.get(code))
            disp = [shown(p, f"place{cyc}") for p in ps]
            rows.append([code, nm, disp[0], disp[1] if len(disp) > 1 else ""])
            for i, p in enumerate(ps[:2], 1):
                ptruth.append([code, i, p])
            if len(ps) > 2:
                for j in range(2, len(ps), 2):
                    chunk = disp[j:j + 2]
                    lead = ["", ""] if blank_style else [code, nm]
                    rows.append(lead + chunk + [""] * (2 - len(chunk)))
                    for k2, p in enumerate(ps[j:j + 2], j + 1):
                        ptruth.append([code, k2, p])
                blank_style = not blank_style
        write_xlsx(d / place_file, ["Trip Code", "Course Name", "Sponsor 1", "Sponsor 2"], rows)

        courses_truth = {}
        for c in offer:
            k = code27(c) if c["name"] not in not_run else "NR:" + norm_course(c["name"])
            courses_truth[k] = dict(type="intl", ran=c["name"] not in not_run)
        for _, code in SG:
            gone = cyc == "2026" and code == MISSING_2026
            courses_truth[code] = dict(type="sg", ran=None if gone else True)   # None = unknown
        truth["courses"][cyc] = courses_truth
        truth["aliases"][cyc] = alias_truth
        truth["placements"][cyc] = ptruth
        placed_prev = {p: (code, None) for code, ps in seats.items() for p in ps}

    truth["expected_checks"]["prior_course_differs_from_previous_placement"] = \
        sum(1 for c in truth["repeaters"]["2027"].values() if "-X" in c)
    truth["special"] = sp
    truth["renumbered_2026_code"] = renumbered
    out.mkdir(parents=True, exist_ok=True)
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    t = generate(Path(a.out).expanduser(), a.seed)
    print(f"wrote {Path(a.out).expanduser() / 'raw'}: {len(t['persons'])} invented people, "
          f"2 cycles; ground truth in truth.json")
