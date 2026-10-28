import pytest

from docketpilot.casefile import find_case_number


@pytest.mark.parametrize(
    ("text", "display", "key"),
    [
        ("IN THE FAMILY COURT, COIMBATORE. H.M.O.P. No. 123 of 2025", "H.M.O.P. No. 123 of 2025", "HMOP-123-2025"),
        ("Crl.O.P.No.45/2024 before the High Court", "Crl.O.P.No.45/2024", "CRLOP-45-2024"),
        ("W.P.(C) No. 1234 of 2023", "W.P.(C) No. 1234 of 2023", "WPC-1234-2023"),
        ("C.C. No. 56/2024", "C.C. No. 56/2024", "CC-56-2024"),
        ("Case: CRL OP/14527/2023 of A Vs B", "CRL OP/14527/2023", "CRLOP-14527-2023"),
        ("O.S. No. 12 of 2020", "O.S. No. 12 of 2020", "OS-12-2020"),
        # real High Court layouts (benchmark findings, decision 32)
        ("THE HONOURABLE SRI JUSTICE K.SURENDER\nCRIMINAL PETITION NO: 2968 OF 2023\nALONG WITH I.A.NO.1 OF 2023",
         "CRIMINAL PETITION NO: 2968 OF 2023", "CRLP-2968-2023"),
        ("1945\nBAIL APPL. NO. 10196 OF 2023\nCRIME NO.771/2023 OF PEROORKADA POLICE STATION",
         "BAIL APPL. NO. 10196 OF 2023", "BA-10196-2023"),
        ("THE HONOURABLE SRI JUSTICE K. SARATH\nWRIT PETITION NO: 2730 0F 2021\nBetween:",
         "WRIT PETITION NO: 2730 0F 2021", "WP-2730-2021"),
        ("CRL OP(MD). No.8017 of 2023\nBEFORE THE MADURAI BENCH ... Cr.No.107/2023", "CRL OP(MD). No.8017 of 2023",
         "CRLOPMD-8017-2023"),
        ("Crl.A. No. 45 of 2024 arising out of S.C. No. 12 of 2019 and C.C. No. 3 of 2018", "Crl.A. No. 45 of 2024",
         "CRLA-45-2024"),
    ],
)
def test_case_numbers(text, display, key):
    cn = find_case_number(text)
    assert cn is not None and cn.display == display and cn.key == key


@pytest.mark.parametrize(
    ("text", "key"),
    [("When is the next hearing in HMOP 214/2026?", "HMOP-214-2026"), ("status of H.M.O.P. 214 of 2026", "HMOP-214-2026"),
     ("CRL.OP 45/2024 next date", "CRLOP-45-2024"), ("W.P.(C) 12/2023", "WPC-12-2023")],
)
def test_short_case_numbers_typed_in_chat(text, key):
    cn = find_case_number(text)
    assert cn is not None and cn.key == key


@pytest.mark.parametrize("text", ["Cheque No. 004512 of 2025", "A/c No. 1234 / 2024", "No case number here.",
                                  "Door No. 12 of 2021", "Section 13 of 1955", "under ACT 26 of 1881",
                                  "Hindu Marriage Act 1955, Section 13(1)", "page 12 of 2020", "2023 INSC 51"])
def test_not_case_numbers(text):
    assert find_case_number(text) is None


def test_same_case_written_differently_matches():
    a = find_case_number("H.M.O.P. No. 123 of 2025")
    b = find_case_number("HMOP No.123/2025")
    assert a and b and a.key == b.key
