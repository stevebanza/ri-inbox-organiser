"""Synthetic demo inbox: .eml files that reproduce the situations met in real use.

Senders, people and file contents are invented. Country names are real (they are the
routing targets), but no attachment contains any real data.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

TARGET = "ri.data@example.org"


@dataclass
class Case:
    key: str
    sender: str
    subject: str
    body: str
    files: list[tuple[str, str, str]]   # (file name, expected country, expected type)
    to: str = TARGET
    inline_logo: bool = False
    note: str = ""


def _payload(name: str) -> bytes:
    """Small dummy file; unique per name so de-duplication works on real content."""
    text = f"district,week,value\nDemo District A,1,0\nDemo District B,1,0\n# {name}\n"
    if name.lower().endswith(".zip"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(Path(name).stem + ".csv", text)
        return buf.getvalue()
    return text.encode()


CASES = [
    Case("uganda_weekly", "Data Manager <data.manager@ug.example>",
         "Measles case-based and lab data, week 20",
         "Dear team,\n\nPlease find this week's files attached.\n\nRegards,\nData manager\n"
         "Ministry of Health, Uganda",
         [("MLABUGA26_WK20.zip", "Uganda", "Lab"), ("MREGUGA26_WK20.zip", "Uganda", "Measles"),
          ("AUGA2620.zip", "Uganda", "AFP")]),
    Case("eritrea_via_ethiopia", "Focal Point <epi.focal@et.example>",
         "Monthly EPI data and AFP database",
         "Dear colleagues,\n\nSharing the monthly files.\n\nBest regards,\nEPI focal point\n"
         "WHO Ethiopia Country Office",
         [("ERI EPI Monthly data by district 2026 March.xls", "Eritrea", "RI"),
          ("EriAFP_2026_03.zip", "Eritrea", "AFP")],
         note="Body and sender say Ethiopia; the files are Eritrea's (ERI, Eri)."),
    Case("malawi_thread_mozambique", "Surveillance Officer <afp.officer@mw.example>",
         "RE: AFP database week 19",
         "Updated database attached.\n\nThanks\n\nFrom: Regional Team\nSent: Monday\n"
         "Subject: AFP database week 19\n\nMozambique, Malawi: please send your AFP "
         "databases by Friday.",
         [("AFP_MAL_2026 database_12 May 2026_ EPI WEEK 19.zip", "Malawi", "AFP")],
         note="Quoted thread names Mozambique first; the file code MAL is Malawi."),
    Case("lesotho_forwarded_by_malawi", "Lab Focal <lab.focal@mw.example>",
         "FW: lab results forward",
         "Forwarding the file received at our Malawi lab this morning.\n\nLab focal point",
         [("MLABLES_Forward (85).zip", "Lesotho", "Lab")],
         note="Sender and body are Malawi; MLABLES = Lesotho lab file."),
    Case("botswana_kpis", "EPI Manager <epi.manager@bw.example>",
         "KPIs by district week 21",
         "Hello,\n\nAttached are this week's KPIs.\n\nKind regards\nEPI Programme, Botswana",
         [("Indicators Formula KPIs by district Week 21-2026.xlsx", "Botswana", "KPIs")],
         inline_logo=True,
         note="No country in the file name: sender domain and signature decide. Logo skipped."),
    Case("botswana_kpis_resent", "EPI Manager <epi.manager@bw.example>",
         "RE: KPIs by district week 21",
         "Resending in case the first one did not arrive.",
         [("Indicators Formula KPIs by district Week 21-2026.xlsx", "Botswana", "KPIs")],
         note="Same file again: recorded as duplicate, not saved twice."),
    Case("regional_two_countries", "Regional Analyst <analyst@example.org>",
         "Quarterly RI data, Kenya and Zambia",
         "Two country files attached.",
         [("Kenya RI data Q1 2026.xlsx", "Kenya", "RI"),
          ("Zambia RI data Q1 2026.xlsx", "Zambia", "RI")],
         note="One email, two countries: each file goes to its own folder."),
    Case("south_sudan", "Surveillance <surv@ss.example>", "Measles data week 20",
         "Attached.\n\nSurveillance unit, South Sudan",
         [("Measles_RSS_Wk20.zip", "South Sudan", "Measles")]),
    Case("mozambique_rubella", "EPI <epi@mz.example>", "Sarampo/Rubéola semana 21",
         "Segue em anexo.", [("Mozambique Measles_Rubella 22.05.2026.xls", "Mozambique",
                              "Measles")]),
    Case("burundi_french", "Point focal PEV <pev@bi.example>",
         "Données PEV du Burundi, mois d'octobre",
         "Bonjour,\n\nCi-joint les données PEV.\n\nCordialement",
         [("BDI_PEV_2026_10.xlsx", "Burundi", "RI")]),
    Case("no_country", "Colleague <someone@example.org>", "Data as requested",
         "See attached.", [("data_final_v2.xlsx", "_Needs_Review", "Other")],
         note="Nothing to go on: review."),
    Case("two_countries_one_file", "Regional Analyst <analyst@example.org>",
         "Namibia and Botswana measles line list", "Combined file attached.",
         [("measles_line_list_combined.xlsx", "_Needs_Review", "Measles")],
         note="One file, two countries in the subject: review, not a guess."),
    Case("body_only", "Colleague <someone@example.org>", "Files",
         "Here is the file we discussed for Zimbabwe.",
         [("district_table.xlsx", "_Needs_Review", "Other")],
         note="A single mention in the body is too weak: review."),
    Case("not_for_us", "Newsletter <news@example.org>", "Uganda newsletter", "News.",
         [("newsletter_Uganda.pdf", "", "")], to="someone.else@example.org",
         note="Not sent to the target address: ignored."),
]


def _logo() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(2048)


def write_demo_inbox(folder: Path, now: datetime | None = None) -> list[Case]:
    folder.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    for i, case in enumerate(CASES):
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = case.sender, case.to, case.subject
        m["Date"] = format_datetime((now - timedelta(hours=len(CASES) - i)).astimezone())
        m["Message-ID"] = make_msgid(domain="demo.example")
        m.set_content(case.body)
        if case.inline_logo:
            m.add_related(_logo(), maintype="image", subtype="png", cid="<logo001>",
                          filename="image001.png")
        for name, _, _ in case.files:
            sub = "zip" if name.endswith(".zip") else "octet-stream"
            m.add_attachment(_payload(name), maintype="application", subtype=sub,
                             filename=name)
        (folder / f"{i + 1:02d}_{case.key}.eml").write_bytes(bytes(m))
    return CASES
