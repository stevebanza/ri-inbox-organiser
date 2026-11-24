"""Tests: every demo situation, the classifier rules, and the file store."""
import io
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from organiser.classify import Classifier, strip_quoted
from organiser.demo import CASES, write_demo_inbox
from organiser.legacy import legacy_country
from organiser.models import Attachment, Message
from organiser.process import process
from organiser.sources import eml_messages
from organiser.store import Store

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("demo")
    write_demo_inbox(tmp / "inbox")
    result = process(eml_messages(tmp / "inbox"), CFG, tmp / "ESA")
    return tmp, result


def _msg(subject="", body="", sender="someone@example.org", files=()):
    return Message("id", subject, body, "", sender, ["ri.data@example.org"], datetime.now(),
                   [Attachment(f, f.encode()) for f in files])


# ---------------------------------------------------------------- demo situations
@pytest.mark.parametrize("case", [c for c in CASES if c.key != "not_for_us"],
                         ids=lambda c: c.key)
def test_each_demo_file_lands_in_the_right_folder(demo, case):
    rows = [r for r in demo[1]["rows"] if r["subject"] == case.subject and r["status"] != "skipped"]
    got = {(r["attachment"], r["country"], r["data_type"]) for r in rows}
    assert got == {(n, c, t) for n, c, t in case.files}


def test_the_three_real_misfilings_are_fixed(demo):
    # The first version filed these in the wrong country folder.
    msgs = {m.subject: m for m in eml_messages(demo[0] / "inbox")}
    for key, wrong in [("eritrea_via_ethiopia", "Ethiopia"),
                       ("malawi_thread_mozambique", "Mozambique"),
                       ("lesotho_forwarded_by_malawi", "Malawi")]:
        case = next(c for c in CASES if c.key == key)
        assert legacy_country(msgs[case.subject]) == wrong
        assert case.files[0][1] != wrong


def test_resent_file_is_a_duplicate_and_logo_is_skipped(demo):
    statuses = [r["status"] for r in demo[1]["rows"]]
    assert statuses.count("duplicate") == 1
    assert statuses.count("skipped") == 1


def test_mail_not_sent_to_target_is_ignored(demo):
    assert demo[1]["counts"]["skipped: not sent to a target address"] == 1


def test_running_again_saves_nothing_new(demo):
    tmp, _ = demo
    before = sorted(p for p in (tmp / "ESA").rglob("*") if p.is_file() and "_" != p.name[0])
    again = process(eml_messages(tmp / "inbox"), CFG, tmp / "ESA")
    after = sorted(p for p in (tmp / "ESA").rglob("*") if p.is_file() and "_" != p.name[0])
    assert again["counts"]["attachments saved"] == 0
    assert before == after


def test_dry_run_writes_nothing(tmp_path):
    write_demo_inbox(tmp_path / "inbox")
    r = process(eml_messages(tmp_path / "inbox"), CFG, tmp_path / "ESA", dry_run=True)
    assert r["counts"]["attachments would save"] == 16   # 17 data files, 1 is a re-send
    assert r["counts"]["attachments duplicate"] == 1
    assert not (tmp_path / "ESA").exists()


# ---------------------------------------------------------------- classifier rules
@pytest.mark.parametrize("name,country", [
    ("AUGA2612.zip", "Uganda"), ("MLABMAL2611.zip", "Malawi"), ("AFPLES_3.zip", "Lesotho"),
    ("EriAFP2026 Aprile_09.zip", "Eritrea"), ("Erimealses_March30_2026.zip", "Eritrea"),
    ("MUGA2553_4.zip", "Uganda"), ("ABOT260311.ZIP", "Botswana"),
    ("MLAMMAL2601.zip", "Malawi"), ("Measles_RSS_Wk_11.zip", "South Sudan"),
])
def test_country_codes_in_file_names(name, country):
    ev = Classifier(CFG).filename_evidence(name)
    assert {e.country for e in ev} == {country}


@pytest.mark.parametrize("name", ["Measles week 21.xlsx", "Malaria report.xlsx",
                                  "Communication tool.docx"])
def test_words_are_not_mistaken_for_codes(name):
    # "Measles" ends in LES, "Malaria" starts with MAL, "Communication" starts with COM.
    assert Classifier(CFG).filename_evidence(name) == []


def test_quoted_thread_is_removed():
    body = "New file attached.\n\nFrom: Regional team\nSent: Monday\nMozambique, please send."
    assert "Mozambique" not in strip_quoted(body)
    assert strip_quoted("> old line\nnew line") == "new line"


def test_file_name_beats_subject_and_sender():
    d = Classifier(CFG).decide(_msg("Malawi weekly data", sender="x@mw.example",
                                    files=["MLABLES_Forward.zip"]), "MLABLES_Forward.zip")
    assert (d.country, d.confidence) == ("Lesotho", "high")


def test_subject_decides_when_file_name_is_silent():
    d = Classifier(CFG).decide(_msg("Kenya RI data, March", files=["data.xlsx"]), "data.xlsx")
    assert (d.country, d.data_type) == ("Kenya", "RI")


def test_data_types():
    c = Classifier(CFG)
    assert c.data_type("MLABUGA26_WK20.zip", "") == "Lab"
    assert c.data_type("MREGUGA26_WK20.zip", "") == "Measles"
    assert c.data_type("AUGA2620.zip", "") == "AFP"
    assert c.data_type("Uganda KPIs by district Week 21.xlsx", "") == "KPIs"
    assert c.data_type("BOT_RI_Data.xls", "") == "RI"
    assert c.data_type("table.xlsx", "Données PEV") == "RI"


# ---------------------------------------------------------------- store
def test_zip_cannot_write_outside_its_folder(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../evil.txt", "x")
        z.writestr("ok.csv", "a,b")
    Store(tmp_path).save(buf.getvalue(), "pack.zip", "Kenya", "RI", extract_zips=True)
    assert (tmp_path / "Kenya" / "RI" / "pack" / "ok.csv").exists()
    assert not any(p.name == "evil.txt" for p in tmp_path.parent.rglob("evil.txt"))


def test_unsafe_characters_in_names(tmp_path):
    status, saved, _ = Store(tmp_path).save(b"1", 'a<b>:c?.xlsx', "Kenya", "RI", False)
    assert status == "saved" and Path(saved).name == "a_b__c_.xlsx"
