"""Phase 0: candidate High Court benches for the pilot corpus (one year profiled in depth)."""
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
YEAR = 2023

# (label, court partition, bench partition)
BENCHES = [
    ("Delhi (DB)", "7_26", "dhcdb"),
    ("Madras (Principal)", "33_10", "hc_cis_mas"),
    ("Madras (Madurai)", "33_10", "mdubench"),
    ("Kerala", "32_4", "highcourtofkerala"),
    ("Bombay (Appellate)", "27_1", "newas"),
    ("Karnataka (Bengaluru)", "29_3", "karnataka_bng_old"),
    ("Punjab & Haryana", "3_22", "phhc"),
    ("Telangana", "36_29", "taphc"),
]


def meta_key(court, bench, year=YEAR):
    return f"metadata/parquet/year={year}/court={court}/bench={bench}/metadata.parquet"


def pdf_key(court, bench, pdf_link, year=YEAR):
    return f"data/pdf/year={year}/court={court}/bench={bench}/{pdf_link.rsplit('/', 1)[-1]}"
