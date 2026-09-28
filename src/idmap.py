"""Shared rules for the Interim pseudonymisation pipeline.

Holds config loading and the path guard, spreadsheet reading, normalisation,
and every rule that decides whether two strings name the same person or the
same course. Nothing here reads raw data on import, and every rule can be
unit-tested without private data (tests/test_matching.py).
"""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "mx", "sir", "madam", "mme"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "edd", "md"}
# compared after lower-casing and removing everything but letters and digits,
# so "N/A.", "n / a", "?" and "--" all count
NULL_TOKENS = {"", "na", "none", "nil", "null", "nan", "nopreference", "noneselected"}
PLACEHOLDER_SPONSORS = NULL_TOKENS | {"tbd", "tba", "tbc", "vacant", "needed", "open",
                                      "unknown", "newhire", "staff", "sponsor", "sponsorneeded"}
NONE_COURSE = "NONE"          # course_id meaning "not a course; drop this preference"
EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(?:\.[a-z0-9\-]+)+")
_HEADER_WORDS = re.compile(
    r"\b(?:e-?mail|address(?:es)?|names?|preferences?|choices?|courses?|codes?|sponsors?|"
    r"text|city|country|prior|rounds?|timestamp|time|questions?|comments?|unnamed|free|trip|"
    r"repeat(?:ing)?|dates?|notes?|id|first|last|second|third|fourth|fifth|sixth|seventh)\b",
    re.I)

# Given-name equivalence classes. A shared class counts as the same given name
# only when the surnames also agree; see name_similarity().
_NICK_GROUPS = [
    {"william", "will", "bill", "billy", "liam"}, {"robert", "rob", "bob", "bobby", "robbie"},
    {"richard", "rich", "rick", "ricky"}, {"james", "jim", "jimmy", "jamie"},
    {"michael", "mike", "mick", "mikey"}, {"christopher", "chris", "topher"},
    {"christine", "christina", "chris", "tina"},
    {"elizabeth", "liz", "lizzie", "beth", "betsy", "eliza", "libby"},
    {"katherine", "catherine", "kathryn", "kate", "katie", "kathy", "cathy", "kat"},
    {"margaret", "maggie", "meg", "peggy"}, {"jennifer", "jen", "jenn", "jenny"},
    {"rebecca", "becky", "becca"}, {"patricia", "pat", "patty", "trish"},
    {"patrick", "pat", "paddy"}, {"matthew", "matt"}, {"thomas", "tom", "tommy"},
    {"anthony", "tony"}, {"andrew", "andy", "drew"}, {"alexander", "alex", "xander"},
    {"alexandra", "alex", "lexi"}, {"samuel", "sam", "sammy"}, {"samantha", "sam", "sammy"},
    {"benjamin", "ben", "benny"}, {"daniel", "dan", "danny"}, {"david", "dave", "davey"},
    {"steven", "stephen", "steve"}, {"joseph", "joe", "joey"}, {"nicholas", "nick", "nicky"},
    {"susan", "sue", "susie"}, {"jonathan", "jon", "jonny"}, {"timothy", "tim"},
    {"edward", "ed", "eddie", "ted", "ned"}, {"gregory", "greg"},
    {"jeffrey", "geoffrey", "jeff", "geoff"}, {"kenneth", "ken", "kenny"},
    {"ronald", "ron", "ronnie"}, {"donald", "don", "donnie"}, {"douglas", "doug"},
    {"frederick", "fred", "freddie"}, {"gerald", "gerry", "jerry"},
    {"lawrence", "laurence", "larry"}, {"leonard", "leo", "len", "lenny"},
    {"martin", "marty"}, {"nathan", "nathaniel", "nate"}, {"peter", "pete"},
    {"philip", "phillip", "phil"}, {"raymond", "ray"}, {"victoria", "vicky", "tori"},
    {"deborah", "debra", "deb", "debbie"}, {"abigail", "abby"}, {"amanda", "mandy"},
    {"barbara", "barb"}, {"cynthia", "cindy"}, {"eleanor", "ellie", "nell"},
    {"frances", "fran"}, {"francis", "frank"}, {"gabriel", "gabe"},
    {"gabrielle", "gabby", "gabi"}, {"jacqueline", "jackie"}, {"judith", "judy"},
    {"kimberly", "kim"}, {"melissa", "mel", "missy"}, {"melanie", "mel"},
    {"pamela", "pam"}, {"sandra", "sandy"}, {"stephanie", "steph"},
    {"theresa", "teresa", "terri", "tess"}, {"zachary", "zach", "zack"},
    {"joshua", "josh"}, {"jacob", "jake"}, {"charles", "charlie", "chuck"},
    {"henry", "hank", "harry"}, {"harold", "harry", "hal"},
    {"allison", "alison", "ally", "allie"}, {"madeline", "madeleine", "maddie"},
]
_NICK: dict[str, set[int]] = {}
for _i, _g in enumerate(_NICK_GROUPS):
    for _n in _g:
        _NICK.setdefault(_n, set()).add(_i)


# --------------------------------------------------------------------------
# config and IO
# --------------------------------------------------------------------------

def _guard(p, what: str) -> Path:
    p = Path(p).expanduser().resolve()
    if p == REPO_ROOT or REPO_ROOT in p.parents:
        raise SystemExit(
            f"REFUSING: {what} {p} is inside the repository ({REPO_ROOT}). "
            "Raw data, the key and derived data must live outside the repo.")
    return p


def load_config(path) -> dict:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    root = _guard(cfg["private_root"], "private_root")
    if not root.is_dir():
        raise SystemExit(f"private_root does not exist: {root}")
    raw = Path(str(cfg.get("raw_dir", "raw"))).expanduser()
    raw = _guard(raw if raw.is_absolute() else root / raw, "raw_dir")
    if not raw.is_dir():
        raise SystemExit(f"raw_dir does not exist: {raw}")
    cfg["_private_root"], cfg["_raw_root"] = root, raw
    cfg["_config_sha256"] = sha256_file(Path(path))
    cfg.setdefault("match_floor", 0.55)
    cfg.setdefault("duplicate_submissions", "last")
    if cfg["duplicate_submissions"] not in {"last", "first", "error"}:
        raise SystemExit("duplicate_submissions must be one of: last, first, error")
    if not cfg.get("cycles"):
        raise SystemExit("config has no cycles")
    cfg["cycles"] = {str(k): v for k, v in cfg["cycles"].items()}
    return cfg


def out_path(cfg, rel: str) -> Path:
    return _guard(cfg["_private_root"] / rel, "output path")


def raw_path(cfg, rel: str) -> Path:
    return _guard(cfg["_raw_root"] / rel, "input path")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon_header(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().casefold()


def shape(v) -> str:
    """'Martin Williams' -> 'Aa Aa'; 'mw@sas.edu.sg' -> 'a@a.a.a'. Reveals no content."""
    s = str(v)
    s = re.sub(r"[A-Z]+", "A", s)
    s = re.sub(r"[a-z]+", "a", s)
    s = re.sub(r"(?:Aa)+", "Aa", s)
    s = re.sub(r"[0-9]+", lambda m: "9" * min(len(m.group()), 4), s)
    return s[:40]


def safe_headers(cols) -> list:
    """Headers for error messages. If the header row is missing, the 'headers'
    are a data row (names, emails), so anything that does not look like a
    header is shown only as its shape."""
    return [c if (_HEADER_WORDS.search(str(c)) and "@" not in str(c)) else f"<{shape(c)}>"
            for c in cols]


def squash(s) -> str:
    """Letters and digits only, any script: 'N/A.' -> 'na', '王伟' -> '王伟'."""
    return re.sub(r"[\W_]", "", strip_accents(s).lower())


def is_null_pref(s) -> bool:
    return squash(s) in NULL_TOKENS


def is_placeholder_sponsor(s) -> bool:
    """TBD, '(new hire)', a dash: anything with no name and no email in it."""
    if squash(s) in PLACEHOLDER_SPONSORS:
        return True
    return not looks_like_email(s) and not norm_name(s)


def read_sheet(path: Path, sheet=None) -> pd.DataFrame:
    """Read one sheet as strings. Headers and cells are whitespace-stripped."""
    if not path.exists():
        raise SystemExit(f"missing input file: {path}")
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        try:
            df = pd.read_excel(path, sheet_name=sheet if sheet is not None else 0, dtype=str)
        except ValueError as exc:
            sheets = pd.ExcelFile(path).sheet_names
            raise SystemExit(f"{path.name}: {exc}. Sheets present: {sheets}") from None
    else:
        df = pd.read_csv(path, dtype=str)
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    dup = sorted({c for c in df.columns if list(df.columns).count(c) > 1})
    if dup:
        raise SystemExit(f"{path.name}: duplicate column headers after trimming spaces: "
                         f"{safe_headers(dup)}")
    df = df.fillna("").astype(str)
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def resolve_col(df: pd.DataFrame, want, label: str):
    """Find a configured column, ignoring case and repeated whitespace."""
    if want is None:
        return None
    if want in df.columns:
        return want
    hits = [c for c in df.columns if canon_header(c) == canon_header(want)]
    if len(hits) == 1:
        return hits[0]
    shown = safe_headers(df.columns)
    hint = ("\n  Some headers look like data (shown as shapes); is the header row missing?"
            if any(str(h).startswith("<") for h in shown) else "")
    raise SystemExit(f"{label}: column {want!r} not found.\n  columns present: {shown}{hint}")


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------

def strip_accents(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s))
                   if not unicodedata.combining(c))


def looks_like_email(s) -> bool:
    return bool(EMAIL_RE.search(strip_accents(s).lower()))


def norm_email(s) -> str:
    """Lower-cased address, extracted from 'Name <addr>' if needed; '' if none."""
    m = EMAIL_RE.search(strip_accents(s).lower())
    return m.group(0).strip(".") if m else ""


def email_local(email: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_email(email).split("@")[0])


def email_domain(email: str) -> str:
    e = norm_email(email)
    return e.split("@", 1)[1] if "@" in e else ""


def norm_name(s) -> str:
    """'Williams, Martin J. (Marty)' -> 'martin j williams'. O'Brien -> obrien."""
    s = str(s).replace("’", "'").replace("`", "'")
    s = strip_accents(s).lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = s.replace("'", "")
    s = "".join(ch if (ch.isalpha() or ch in ",-. \t") else " " for ch in s)   # any script
    if s.count(",") == 1:
        last, _, first = s.partition(",")
        s = f"{first} {last}"
    toks = [t for t in re.split(r"[\s\-.,]+", s) if t]
    toks = [t for t in toks if t not in TITLES and t not in SUFFIXES]
    return " ".join(toks)


def norm_course(s) -> str:
    s = strip_accents(s).lower().replace("&", " and ")
    s = re.sub(r"[\W_]+", " ", s)
    return " ".join(s.split())


# "(MALE)" / "(FEMALE)" after a course name on the forms marks which sponsor slot is
# open: every course needs at least one male and one female sponsor, so once one is
# pre-allocated only the other gender's slot is offered. Only the bracketed full word
# counts, so a destination such as "Maldives - Male" is never cut.
SLOT_TAG_RE = re.compile(r"\s*[\(\[]\s*(male|female)\s*[\)\]]\s*$", re.I)


def split_slot_tag(s) -> tuple[str, str]:
    """'Nepal Trek (MALE)' -> ('Nepal Trek', 'male'); untagged -> (s, '')."""
    s = str(s).strip()
    m = SLOT_TAG_RE.search(s)
    if not m or not s[: m.start()].strip():
        return s, ""
    return s[: m.start()].strip(), m.group(1).lower()


def course_key(s) -> str:
    """Key for a course string on a form: the slot tag is not part of the course."""
    return norm_course(split_slot_tag(s)[0])


def norm_code(s) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_accents(s).lower())


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# --------------------------------------------------------------------------
# people
# --------------------------------------------------------------------------

def _name_keys(n: str):
    """Email local parts a normalised name could plausibly produce."""
    toks = n.split()
    if not toks:
        return set(), set()
    first, last, rest, mid = toks[0], toks[-1], toks[1:], toks[1:-1]
    strong = {first + last, last + first, first[0] + last, last + first[0], first + last[0]}
    if mid:
        strong |= {first + "".join(t[0] for t in mid) + last, first[0] + mid[0][0] + last,
                   first + "".join(rest), first[0] + "".join(rest)}
    weak = {last, first}
    if len(toks) > 1:
        weak |= {first[0] + rest[0],                                  # first part of a double surname
                 first + "".join(t[0] for t in rest),                  # surname-first: tanwm
                 "".join(t[0] for t in rest) + first,                  # wmtan
                 "".join(rest) + first}                                # weimingtan
    weak -= strong
    return strong, weak


def match_score(email: str, name: str) -> tuple[str, float]:
    """How well an email address fits a name. Returns (method, score in [0, 1])."""
    local = email_local(email)
    if not local:
        return "no_local_part", 0.0
    bare = re.sub(r"\d+$", "", local) or local        # dkim2 -> dkim
    n = norm_name(name)
    strong, weak = _name_keys(n)
    if local in strong or bare in strong:
        return "exact_key", 1.0
    if local in weak or bare in weak:
        return "weak_key", 0.72
    flat = n.replace(" ", "")
    if not flat:
        return "no_name", 0.0
    r = _ratio(bare, flat)
    if flat.startswith(bare) or flat.endswith(bare):
        r = min(1.0, r + 0.05)
    return "fuzzy", round(r, 4)


def nick_equiv(a: str, b: str) -> bool:
    return bool(_NICK.get(a, set()) & _NICK.get(b, set()))


def name_similarity(a: str, b: str) -> float:
    """Similarity of two normalised names, tuned to be conservative.

    >= 0.75 means "plausibly the same person written differently"; below that
    a merge is never proposed. Same surname plus same initial alone is 0.5, so
    Daniel Kim and David Kim are never merged on names.
    """
    if a == b:
        return 1.0
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return 0.0
    if sorted(ta) == sorted(tb):
        return 0.9
    fa, la, fb, lb = ta[0], ta[-1], tb[0], tb[-1]
    if fa == fb and la == lb:
        return 0.95                                   # middle name or initial differs
    if la == lb:
        if nick_equiv(fa, fb):
            return 0.85
        short, long_ = sorted((fa, fb), key=len)
        if len(short) >= 3 and long_.startswith(short):
            return 0.85                               # dan / daniel
        if min(len(fa), len(fb)) > 2 and _ratio(fa, fb) >= 0.85:
            return 0.75                               # jonathon / jonathan
        return 0.5 if fa[0] == fb[0] else 0.2
    if fa == fb:
        if set(ta[1:]) & set(tb[1:]):
            return 0.8                                # garcia lopez / garcia
        if _ratio(la, lb) >= 0.85:
            return 0.75                               # surname typo
        return 0.1
    return 0.0


# --------------------------------------------------------------------------
# courses
# --------------------------------------------------------------------------

_STOP = {"and", "the", "of", "in", "a", "an", "to", "for", "with", "on", "at"}


def tokens_covered(a: str, b: str) -> bool:
    """Every meaningful word of the shorter name has a near-identical twin in the other.

    Stops 'Chile Rainforest Ecology' matching 'Laos Rainforest Ecology' (0.85 by
    character similarity) while still allowing 'Mairne' for 'Marine'. Words
    containing digits must match exactly, so 'Trip 1' never matches 'Trip 2'.
    """
    ta, tb = a.split(), b.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    for t in short:
        if t in _STOP:
            continue
        if any(ch.isdigit() for ch in t):
            if t not in long_:
                return False
            continue
        if len(t) <= 2:
            continue
        if not any(t == u or (len(t) > 3 and len(u) > 3 and _ratio(t, u) >= 0.75) for u in long_):
            return False
    return True


def _contiguous(needle, hay) -> bool:
    n = len(needle)
    return n > 0 and any(tuple(hay[i:i + n]) == tuple(needle) for i in range(len(hay) - n + 1))


def phrase_in(phrase: str, text: str) -> bool:
    """Whole-token containment of one normalised phrase in another."""
    return bool(phrase) and _contiguous(phrase.split(), text.split())


class CourseIndex:
    """Resolve a free string to one course id by code, name, containment or similarity."""

    def __init__(self):
        self.by_name: dict[str, set] = {}
        self.by_code: dict[str, set] = {}
        self.code_res: list = []
        self.name_toks: list = []

    def add(self, course_id: str, names=(), codes=()):
        for nm in names:
            k = norm_course(nm)
            if k:
                self.by_name.setdefault(k, set()).add(course_id)
                self.name_toks.append((tuple(k.split()), course_id))
        for c in codes:
            k = norm_code(c)
            if not k:
                continue
            self.by_code.setdefault(k, set()).add(course_id)
            groups = re.findall(r"[a-z0-9]+", strip_accents(c).lower())
            # Only distinctive codes are searched for inside longer strings: "NPL-TRK" or
            # "INT032" yes, "101" or "ART" no (they occur naturally in course names).
            distinctive = len(groups) >= 2 or (re.search(r"[a-z]", k) and re.search(r"\d", k))
            if distinctive:
                pat = r"(?<![a-z0-9])" + r"[\s\-_/.]*".join(map(re.escape, groups)) + r"(?![a-z0-9])"
                self.code_res.append((re.compile(pat), course_id))

    def __len__(self):
        return len({c for ids in self.by_name.values() for c in ids} |
                   {c for ids in self.by_code.values() for c in ids})

    def match(self, s) -> tuple[str, str, float, object]:
        """Return (course_id, method, score, margin). course_id is '' when unresolved.

        Upper-case methods need a human decision; lower-case ones need a check.
        """
        raw = split_slot_tag(s)[0]  # "(MALE)"/"(FEMALE)" names a slot, not a course
        n = norm_course(raw)
        if not n:
            return "", "blank", 0.0, ""

        hit = self.by_name.get(n)
        if hit:
            if len(hit) == 1:
                return next(iter(hit)), "exact_name", 1.0, ""
            return "", "AMBIGUOUS_DUPLICATE_NAME", 0.0, ""

        hit = self.by_code.get(norm_code(raw))
        if hit:
            if len(hit) == 1:
                return next(iter(hit)), "exact_code", 1.0, ""
            return "", "AMBIGUOUS_DUPLICATE_CODE", 0.0, ""

        low = strip_accents(raw).lower()
        in_str = {cid for rx, cid in self.code_res if rx.search(low)}
        if len(in_str) > 1:
            return "", "AMBIGUOUS_MULTIPLE_CODES", 0.0, ""

        toks = n.split()
        contained = [(len(t), cid) for t, cid in self.name_toks if _contiguous(t, toks)]
        name_ids = set()
        if contained:
            best = max(l for l, _ in contained)
            name_ids = {cid for l, cid in contained if l == best}

        if in_str:
            cid = next(iter(in_str))
            if name_ids and cid not in name_ids:
                return "", "AMBIGUOUS_CODE_VS_NAME", 0.0, ""
            return cid, "code_in_string", 0.95, ""
        if name_ids:
            if len(name_ids) == 1:
                return name_ids.pop(), "name_in_string", 0.9, ""
            return "", "AMBIGUOUS_CONTAINED", 0.0, ""

        within = {cid for t, cid in self.name_toks if _contiguous(toks, t)}
        if len(within) == 1:
            return within.pop(), "string_in_name", 0.85, ""
        if len(within) > 1:
            return "", "AMBIGUOUS_PARTIAL", 0.0, ""

        best_by_id: dict[str, float] = {}
        nearest = 0.0
        for k, ids in self.by_name.items():
            r = _ratio(n, k)
            nearest = max(nearest, r)
            if r < 0.8 or not tokens_covered(n, k):
                continue
            for cid in ids:
                best_by_id[cid] = max(best_by_id.get(cid, 0.0), r)
        ranked = sorted(best_by_id.items(), key=lambda kv: (-kv[1], kv[0]))
        if not ranked:
            return "", "UNMATCHED", round(nearest, 3), ""
        (bid, b), second = ranked[0], (ranked[1][1] if len(ranked) > 1 else 0.0)
        margin = round(b - second, 3)
        return bid, ("fuzzy" if margin >= 0.08 else "FUZZY_THIN_MARGIN"), round(b, 3), margin


def needs_review(method: str) -> bool:
    return any(ch.isupper() for ch in method)
