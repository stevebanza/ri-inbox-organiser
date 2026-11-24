"""Decide which country and which data type each attachment belongs to.

Evidence, strongest first:
  1. the attachment's own file name: a country code (ERI, MAL, UGA, RSS...) or name
  2. the email subject
  3. the sender's e-mail domain
  4. the body, with quoted replies and forwarded threads removed
A file-name match for exactly one country decides on its own. Otherwise the scores of
all sources are added; a weak score or a near-tie goes to review instead of a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import Message

REVIEW = "_Needs_Review"

QUOTE_MARKERS = re.compile(
    r"^\s*(-{2,}\s*Original Message|From:|De\s?:|Sent:|Envoy[ée]\s?:|On .+ wrote:|"
    r"Le .+ a [ée]crit\s?:|_{5,})", re.IGNORECASE | re.MULTILINE)


@dataclass
class Evidence:
    source: str      # filename | subject | sender | body
    country: str
    term: str
    weight: float


@dataclass
class Decision:
    country: str
    data_type: str
    confidence: str  # high | medium | review
    reason: str
    evidence: list[Evidence] = field(default_factory=list)


def strip_quoted(body: str) -> str:
    """Keep only the newest part of the message: drop '>' lines and everything after the
    first reply/forward header (signatures of earlier senders often name other countries)."""
    m = QUOTE_MARKERS.search(body)
    text = body[: m.start()] if m else body
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


class Classifier:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.weights = cfg["weights"]
        self.name_patterns: list[tuple[re.Pattern, str, str]] = []
        self.code_of: dict[str, str] = {}
        self.domains: list[tuple[str, str]] = []
        for country, spec in cfg["countries"].items():
            for term in [country, *spec.get("aliases", [])]:
                words = re.escape(term).replace(r"\ ", r"[\s_\-]+")
                self.name_patterns.append(
                    (re.compile(rf"(?<![A-Za-z]){words}(?![A-Za-z])", re.IGNORECASE),
                     country, term))
            for code in spec.get("codes", []):
                self.code_of[code.upper()] = country
            for d in spec.get("domains", []):
                self.domains.append((d.lower(), country))
        self.name_patterns.sort(key=lambda p: -len(p[2]))
        pre = "|".join(sorted(cfg["filename_code_prefixes"], key=len, reverse=True))
        suf = "|".join(sorted(cfg["filename_code_suffixes"], key=len, reverse=True))
        codes = "|".join(sorted(self.code_of, key=len, reverse=True))
        self.code_token = re.compile(rf"^(?:{pre})?({codes})(?:{suf})?$")
        self.types = [(t["name"], re.compile(t["pattern"], re.IGNORECASE))
                      for t in cfg["data_types"]]

    # ---------------------------------------------------------------- evidence
    def _names_in(self, text: str, source: str) -> list[Evidence]:
        found, taken = [], []
        for pattern, country, _term in self.name_patterns:
            for m in pattern.finditer(text):
                if any(a <= m.start() < b for a, b in taken):  # "South Sudan" not also "Sudan"
                    continue
                taken.append((m.start(), m.end()))
                found.append(Evidence(source, country, m.group(0), self.weights[source]))
        return found

    def filename_evidence(self, filename: str) -> list[Evidence]:
        stem = Path(filename).stem
        ev = self._names_in(stem, "filename")
        for token in re.split(r"[^A-Za-z]+", stem):
            m = self.code_token.match(token.upper())
            if m:
                ev.append(Evidence("filename", self.code_of[m.group(1)], token,
                                   self.weights["filename"]))
        return ev

    def message_evidence(self, msg: Message) -> list[Evidence]:
        ev = self._names_in(msg.subject, "subject")
        domain = msg.sender_email.rsplit("@", 1)[-1]
        for d, country in self.domains:
            if domain == d or domain.endswith("." + d):
                ev.append(Evidence("sender", country, domain, self.weights["sender"]))
        ev += self._names_in(strip_quoted(msg.body)[: self.cfg["body_chars"]], "body")
        return ev

    # ---------------------------------------------------------------- decisions
    def data_type(self, filename: str, subject: str) -> str:
        for text in (Path(filename).stem, subject):
            for name, pattern in self.types:
                if pattern.search(text):
                    return name
        return "Other"

    def decide(self, msg: Message, filename: str) -> Decision:
        file_ev = self.filename_evidence(filename)
        msg_ev = self.message_evidence(msg)
        dtype = self.data_type(filename, msg.subject)
        file_countries = {e.country for e in file_ev}
        if len(file_countries) == 1:
            c = file_countries.pop()
            terms = ", ".join(sorted({e.term for e in file_ev}))
            return Decision(c, dtype, "high", f"file name: {terms}", file_ev + msg_ev)

        # No single answer in the file name: add up every source (one hit per source).
        scores: dict[str, float] = {}
        seen = set()
        for e in file_ev + msg_ev:
            if (e.source, e.country) not in seen:
                seen.add((e.source, e.country))
                scores[e.country] = scores.get(e.country, 0) + e.weight
        if not scores:
            return Decision(REVIEW, dtype, "review", "no country found in file name, subject, "
                            "sender or message", msg_ev)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        best, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        if top < self.cfg["min_score"]:
            return Decision(REVIEW, dtype, "review", f"weak evidence: only the message body "
                            f"mentions {best}", file_ev + msg_ev)
        if second >= top * self.cfg["tie_ratio"]:
            names = " / ".join(c for c, s in ranked if s >= top * self.cfg["tie_ratio"])
            return Decision(REVIEW, dtype, "review", f"several countries: {names}",
                            file_ev + msg_ev)
        srcs = sorted({e.source for e in file_ev + msg_ev if e.country == best})
        return Decision(best, dtype, "medium", f"{' + '.join(srcs)} (score {top:g})",
                        file_ev + msg_ev)
