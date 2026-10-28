"""Redaction, restore and vault. Synthetic values only."""
import pytest

from docketpilot.config import get_settings
from docketpilot.privacy import vault
from docketpilot.privacy.redact import detect, redact, restore, verhoeff_digit, verhoeff_valid


def test_verhoeff():
    base = "23456789012"
    full = base + verhoeff_digit(base)
    assert verhoeff_valid(full)
    bad = full[:-1] + str((int(full[-1]) + 1) % 10)
    assert not verhoeff_valid(bad)


def test_aadhaar_needs_valid_checksum():
    base = "23456789012"
    good = base + verhoeff_digit(base)
    bad = base + str((int(verhoeff_digit(base)) + 1) % 10)
    types_good = {e.type for e in detect(f"Aadhaar {good[:4]} {good[4:8]} {good[8:]}", use_ner=False)}
    types_bad = {e.type for e in detect(f"Number {bad[:4]} {bad[4:8]} {bad[8:]}", use_ner=False)}
    assert "AADHAAR" in types_good and "AADHAAR" not in types_bad


@pytest.mark.parametrize(
    ("text", "typ"),
    [("PAN ABCPK1234Z", "PAN"), ("call 9876543210", "PHONE"), ("call +91 98765 43210", "PHONE"),
     ("mail x.y@example.com", "EMAIL"), ("IFSC HDFC0001234", "IFSC"), ("A/c No. 123456789012", "BANK_ACCOUNT"),
     ("vehicle TN 37 AB 1234", "VEHICLE"), ("Mr. Ramesh Kumar", "PERSON"), ("S/o Suresh Iyer", "PERSON"),
     ("M/s Kaveri Textiles Pvt. Ltd.", "ORG"), ("No. 12, Gandhi Road, Coimbatore - 641001", "ADDRESS")],
)
def test_rule_recognisers(text, typ):
    assert typ in {e.type for e in detect(text, use_ner=False)}


def test_address_does_not_swallow_cheque_details():
    text = ("Mr. Karthik Subramanian gave cheque No. 778812 dated 02-09-2026 for Rs. 1,80,000 to Mrs. Deepa "
            "Natarajan, residing at No. 21, Temple Street, Madurai - 625001.")
    red = redact(text, use_ner=False)
    assert "778812" in red.text and "02-09-2026" in red.text and "1,80,000" in red.text  # facts kept for drafting
    addr = [e.value for e in red.entities if e.type == "ADDRESS"]
    assert addr == ["No. 21, Temple Street, Madurai - 625001"]
    assert "Deepa" not in red.text and "Karthik" not in red.text


def test_law_and_courts_are_not_masked():
    red = redact("Section 138 of the Negotiable Instruments Act before the High Court of Madras.")
    assert "Negotiable Instruments Act" in red.text and "High Court" in red.text


def test_placeholders_are_consistent_and_restore_roundtrips():
    text = "Mr. Ramesh Kumar paid. Later Mr. Ramesh Kumar asked Mr. Suresh Iyer, phone 9876543210."
    red = redact(text, use_ner=False)
    assert red.text.count("PERSON_1") == 2 and "PERSON_2" in red.text and "PHONE_1" in red.text
    assert "Ramesh" not in red.text and "9876543210" not in red.text
    assert restore(red.text, red.mapping) == text


def test_existing_mapping_reused_across_documents():
    first = redact("Mr. Ramesh Kumar", use_ner=False)
    second = redact("Mr. Arun Das met Mr. Ramesh Kumar", mapping=first.mapping, use_ner=False)
    assert "PERSON_1" in second.text and "PERSON_2" in second.text
    assert second.mapping["PERSON_1"] == "Ramesh Kumar" and second.mapping["PERSON_2"] == "Arun Das"


def test_lawyer_can_add_and_unmask():
    red = redact("Kalyan paid Mr. Ramesh Kumar.", extra=[("PERSON", "Kalyan")], unmask={"Ramesh Kumar"},
                 use_ner=False)
    assert "Kalyan" not in red.text and "Ramesh Kumar" in red.text


def test_restore_does_not_break_longer_placeholders():
    mapping = {f"PERSON_{i}": f"Name{i}" for i in range(1, 13)}
    assert restore("PERSON_1 and PERSON_12", mapping) == "Name1 and Name12"


def test_vault_roundtrip_and_encryption(tmp_path, monkeypatch):
    if get_settings().vault_key is None:
        pytest.skip("VAULT_KEY not set")
    monkeypatch.setattr(vault, "VAULT_DIR", tmp_path)
    vault.save("matter-1", {"PERSON_1": "Ramesh Kumar"})
    raw = (tmp_path / "matter-1.vault").read_bytes()
    assert b"Ramesh" not in raw
    assert vault.load("matter-1") == {"PERSON_1": "Ramesh Kumar"}
    vault.delete("matter-1")
    assert vault.load("matter-1") == {}


def test_vault_rejects_path_tricks():
    with pytest.raises(vault.VaultError):
        vault.load("../..")
