"""Download the prototype corpus from the AWS open-data buckets (resumable, parallel).

Prototype scope (decisions 10 and 27 in docs/DECISIONS.md), well under the 10 GB cap:
  * SC: every English judgment PDF for 2015-2026 (~10,000 files).
  * HC: per pilot bench per year (2023-2024), a random sample of criminal matters and a random sample of
    civil / family / writ / motor-accident / arbitration matters, so the library is not cheque-bounce only.
Each PDF's text is extracted right after download and saved next to it as .txt.

Usage:  python -m docketpilot.ingestion.download [--hc-per-bench-year N] [--civil-per-bench-year N]
            [--sc-from YEAR]
"""
import argparse
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config
from pypdf import PdfReader

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
SC_BUCKET = "indian-supreme-court-judgments"
HC_BUCKET = "indian-high-court-judgments"
SC_YEARS = range(2015, 2027)
HC_YEARS = (2023, 2024)
HC_BENCHES = [  # (label, court, bench) -- pilot courts chosen in Phase 0
    ("Kerala", "32_4", "highcourtofkerala"),
    ("Karnataka", "29_3", "karnataka_bng_old"),
    ("Telangana", "36_29", "taphc"),
    ("Madras", "33_10", "hc_cis_mas"),
    ("Madras (Madurai)", "33_10", "mdubench"),
]
CRIMINAL = re.compile(r"CRL|CRM|CRR|CRA|REVN|APEAL|^APL|BAIL|HCP")
# Civil side, weighted toward what a general practice sees: family, civil appeals/revisions, writs, motor
# accident, arbitration, consumer, rent, land acquisition.
FAMILY = re.compile(r"FC|MAT|RPFC|HMOP|GWOP|DVC")  # writs dominate a random draw, so family is sampled first
CIVIL = re.compile(r"FC|MAT|RPFC|HMOP|^WP(?!.*CRL)|^WA|RSA|RFA|^SA|^AS|CRP|CMA|MFA|MACA|MACMA|ARB|COM|RC|LA|^OP|^CS")

logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are harmless and flood the log

s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(signature_version=UNSIGNED, retries={"max_attempts": 10, "mode": "adaptive"},
                  read_timeout=300, max_pool_connections=32),
)


def extract_text(pdf: Path) -> None:
    txt = pdf.with_suffix(".txt")
    if txt.exists():
        return
    pages = [p.extract_text() or "" for p in PdfReader(str(pdf)).pages]
    txt.write_text("\n\f\n".join(pages), encoding="utf-8")  # \f marks page breaks


def fetch(bucket: str, key: str, dest: Path) -> str:
    try:
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            s3.download_file(bucket, key, str(tmp))
            tmp.replace(dest)
        extract_text(dest)
        return "ok"
    except Exception as e:  # one bad file must not stop the run; it is logged in the manifest
        return f"error: {type(e).__name__}: {str(e)[:100]}"


def sc_jobs(from_year: int = SC_YEARS.start) -> list[tuple[str, str, Path, dict]]:
    jobs = []
    for year in sorted(SC_YEARS, reverse=True):  # newest first
        if year < from_year:
            continue
        meta = RAW / "sc_metadata" / "metadata" / "parquet" / f"year={year}" / "metadata.parquet"
        if not meta.exists():
            meta.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(SC_BUCKET, f"metadata/parquet/year={year}/metadata.parquet", str(meta))
        for path in pd.read_parquet(meta, columns=["path"])["path"]:
            key = f"data/pdf/year={year}/english/{path}_EN.pdf"
            jobs.append((SC_BUCKET, key, RAW / "sc_pdf" / str(year) / f"{path}_EN.pdf",
                         {"court": "SC", "year": year, "path": path}))
    return jobs


def hc_meta(year: int, court: str, bench: str) -> pd.DataFrame:
    key = f"metadata/parquet/year={year}/court={court}/bench={bench}/metadata.parquet"
    dest = RAW / "hc_metadata" / key
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(HC_BUCKET, key, str(dest))
    return pd.read_parquet(dest, columns=["title", "pdf_link", "cnr"])


def hc_jobs(per_bench_year: int, civil_per_bench_year: int = 0, years: tuple[int, ...] = HC_YEARS) -> list[tuple[str, str, Path, dict]]:
    jobs = []
    for label, court, bench in HC_BENCHES:
        for year in years:
            df = hc_meta(year, court, bench)
            types = df.title.fillna("").str.extract(r"^\s*([^/]+?)\s*/")[0].str.upper().fillna("")
            crim = df[types.str.contains(CRIMINAL)]
            civil = df[~types.str.contains(CRIMINAL) & types.str.contains(CIVIL)]
            picks = [crim.sample(min(per_bench_year, len(crim)), random_state=2024)]
            if civil_per_bench_year:
                fam = civil[types[civil.index].str.contains(FAMILY)]
                fam = fam.sample(min(civil_per_bench_year // 3, len(fam)), random_state=2025)
                rest = civil.drop(fam.index)
                picks += [fam, rest.sample(min(civil_per_bench_year - len(fam), len(rest)), random_state=2025)]
            for part in picks:
                for r in part.itertuples():
                    name = r.pdf_link.rsplit("/", 1)[-1]
                    key = f"data/pdf/year={year}/court={court}/bench={bench}/{name}"
                    jobs.append((HC_BUCKET, key, RAW / "hc_pdf" / bench / str(year) / name,
                                 {"court": label, "bench": bench, "year": year, "cnr": r.cnr}))
            print(f"queued {label} {year}: {min(per_bench_year, len(crim))} criminal, "
                  f"{min(civil_per_bench_year, len(civil))} civil/family/writ", flush=True)
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hc-per-bench-year", type=int, default=300)
    ap.add_argument("--civil-per-bench-year", type=int, default=500)
    ap.add_argument("--sc-from", type=int, default=SC_YEARS.start)
    ap.add_argument("--hc-years", type=int, nargs="+", default=list(HC_YEARS))
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    # Order is priority: small, s.138-rich HC files first, then SC newest first. The link is slow
    # (~0.3 MB/s), so whatever has arrived can be loaded while the rest continues.
    jobs = hc_jobs(args.hc_per_bench_year, args.civil_per_bench_year, tuple(args.hc_years)) + sc_jobs(args.sc_from)
    print(f"{len(jobs)} files to fetch", flush=True)
    manifest = RAW / "download_manifest.jsonl"
    done = errors = 0
    with ThreadPoolExecutor(args.workers) as pool, manifest.open("a", encoding="utf-8") as log:
        futures = {pool.submit(fetch, b, k, d): (k, meta) for b, k, d, meta in jobs}
        for f in as_completed(futures):
            key, meta = futures[f]
            status = f.result()
            done += 1
            errors += status != "ok"
            log.write(json.dumps({"key": key, "status": status, **meta}) + "\n")
            if done % 250 == 0:
                print(f"{done}/{len(jobs)} done, {errors} errors", flush=True)
    print(f"finished: {done} files, {errors} errors", flush=True)


if __name__ == "__main__":
    main()
