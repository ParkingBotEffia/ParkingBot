"""Parser tests against REAL EFFIA HTML captured from the live site."""

import os

from parkingbot.parse import available_count, parse_lots

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def test_all_unavailable_fixture():
    lots = parse_lots(_load("valserhone_all_unavailable.html"))
    # All four monitored lots are present and identified.
    assert {lot.code for lot in lots} == {"P1", "P2", "P3", "P4"}
    # None available -> matches EFFIA's "0 parking(s) disponible(s)".
    assert available_count(lots) == 0
    assert all(not lot.available for lot in lots)
    # URLs are cleaned of the query string and point at the right lot.
    p4 = next(lot for lot in lots if lot.code == "P4")
    assert p4.url.endswith("-p4-effia")
    assert "?" not in p4.url


def test_p4_available_fixture():
    lots = parse_lots(_load("valserhone_p4_available.html"))
    assert available_count(lots) == 1
    available = [lot for lot in lots if lot.available]
    assert len(available) == 1 and available[0].code == "P4"
