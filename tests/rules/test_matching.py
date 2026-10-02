"""Unit tests for the matching rules. No private data needed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stable_sponsors.pseudonymize.idmap import (  # noqa: E402
    CourseIndex,
    match_score,
    name_similarity,
    norm_course,
    norm_email,
    norm_name,
    tokens_covered,
)


def test_norm_name_forms():
    assert norm_name("Williams, Martin J. (Marty)") == "martin j williams"
    assert norm_name("Sean O’Brien") == "sean obrien"
    assert norm_name("Maria Garcia-Lopez") == "maria garcia lopez"
    assert norm_name("  Dr. José  Núñez ") == "jose nunez"
    assert norm_name("Tan, Grace") == norm_name("grace tan")


def test_norm_email_extracts_address():
    assert (
        norm_email("Martin Williams <MWilliams@SAS.edu.sg>") == "mwilliams@sas.edu.sg"
    )
    assert norm_email("not an address") == ""


def test_email_keys():
    assert match_score("mwilliams@sas.edu.sg", "Martin Williams") == ("exact_key", 1.0)
    assert match_score("dkim2@sas.edu.sg", "David Kim")[1] == 1.0  # digit suffix
    assert match_score("sobrien@sas.edu.sg", "Sean O'Brien")[1] == 1.0
    assert match_score("mgarcialopez@sas.edu.sg", "Maria Garcia-Lopez")[1] == 1.0
    assert match_score("weiming.tan@sas.edu.sg", "Tan Wei Ming")[0] == "weak_key"
    assert match_score("mwilliams@sas.edu.sg", "Priya Nathan")[1] < 0.55


def test_name_similarity_is_conservative():
    assert name_similarity("marty williams", "martin williams") >= 0.75  # nickname
    assert name_similarity("dan kim", "daniel kim") >= 0.75  # prefix
    assert name_similarity("grace l tan", "grace tan") >= 0.75  # middle initial
    assert (
        name_similarity("maria garcia lopez", "maria garcia") >= 0.75
    )  # double surname
    assert name_similarity("williams martin", "martin williams") >= 0.75  # order
    assert name_similarity("daniel kim", "david kim") < 0.75  # same initial only
    assert name_similarity("mary williams", "martin williams") < 0.75
    assert name_similarity("grace tan", "gina tan") < 0.75


def test_tokens_covered():
    assert tokens_covered("belize mairne conservation", "belize marine conservation")
    assert not tokens_covered("chile rainforest ecology", "laos rainforest ecology")
    assert not tokens_covered("bali trip 1", "bali trip 2")


def _idx():
    ix = CourseIndex()
    ix.add("INT003", ["Nepal Trek"], ["INT003"])
    ix.add("INT032", ["Nepal Trek Advanced"], ["INT032"])
    ix.add("NPL-TRK", ["Bhutan Mountain Trek"], ["NPL-TRK"])
    ix.add("SGP004", ["Coastal Cleanup"], ["SGP004"])
    ix.add("LAO-ECO", ["Laos Rainforest Ecology"], ["LAO-ECO"])
    return ix


def test_course_matching_cases():
    ix = _idx()
    m = lambda s: ix.match(s)[:2]  # noqa: E731
    assert m("INT032 - Nepal Trek Advanced") == ("INT032", "code_in_string")
    assert m("Nepal Trek Advanced") == ("INT032", "exact_name")
    assert m("Nepal Trek") == ("INT003", "exact_name")  # not the longer one
    assert m("INT003") == ("INT003", "exact_code")
    assert m("npl-trk") == ("NPL-TRK", "exact_code")  # hyphenated code
    assert m("NPL TRK (Bhutan)")[0] == "NPL-TRK"  # code inside a string
    assert m("Nepal Trek (Kathmandu, Feb 2027)") == ("INT003", "name_in_string")
    assert m("Coastal Clean-up")[0] == "SGP004"
    assert m("INT003 / INT032 combined")[1] == "AMBIGUOUS_MULTIPLE_CODES"
    assert m("Chile Rainforest Ecology") == ("", "UNMATCHED")  # other country
    assert m("Kayaking in Krabi") == ("", "UNMATCHED")


def test_norm_course_ampersand():
    assert norm_course("Arts & Heritage") == norm_course("Arts and Heritage")


def test_slot_tags():
    from stable_sponsors.pseudonymize.idmap import course_key, split_slot_tag

    assert split_slot_tag("Nepal Trek (MALE)") == ("Nepal Trek", "male")
    assert split_slot_tag("Nepal Trek [Female] ") == ("Nepal Trek", "female")
    assert split_slot_tag("Maldives - Male") == ("Maldives - Male", "")
    assert split_slot_tag("(MALE)") == ("(MALE)", "")
    assert (
        course_key("Nepal Trek (MALE)")
        == course_key("nepal trek")
        == course_key("Nepal Trek (female)")
    )
    ix = CourseIndex()
    ix.add("NPL-TRK", ["Nepal Trek"], ["NPL-TRK"])
    ix.add("NPL-ADV", ["Nepal Trek Advanced"], ["NPL-ADV"])
    assert ix.match("Nepal Trek (MALE)")[:2] == ("NPL-TRK", "exact_name")
    assert ix.match("Nepal Trek Advanced (FEMALE)")[:2] == ("NPL-ADV", "exact_name")
