"""The first version's rule, kept only to compare results: join subject, body, sender,
recipients and file names into one text, then take the longest country name found
anywhere in it. File-name codes are not read and quoted threads are not removed."""
from __future__ import annotations

import re

from .models import Message

V1_COUNTRIES = ["Botswana", "Burundi", "Comoros", "Ethiopia", "Eswatini", "Kenya", "Lesotho",
                "Madagascar", "Malawi", "Mozambique", "Namibia", "Rwanda", "Somalia",
                "South Africa", "South Sudan", "Tanzania", "Uganda", "Zambia", "Zimbabwe"]


def legacy_country(msg: Message) -> str:
    text = "\n".join([msg.subject, msg.body, msg.sender_name, msg.sender_email,
                      "; ".join(msg.recipients), " ".join(a.name for a in msg.attachments)])
    for term in sorted(V1_COUNTRIES, key=len, reverse=True):
        words = re.escape(term).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![A-Za-z]){words}(?![A-Za-z])", text, re.IGNORECASE):
            return term
    return "_Needs_Review"
