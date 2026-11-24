"""Go through the messages, classify and save each attachment, and report."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .classify import Classifier
from .models import Message
from .store import Store

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".emz", ".wmz"}


def sent_to_target(msg: Message, targets: list[str]) -> bool:
    if not targets:
        return True
    want = {t.lower().strip() for t in targets}
    return any(r in want for r in msg.recipients)


def is_decoration(att, min_image_kb: float) -> bool:
    """Signature logos and pasted pictures, not data."""
    return att.inline or (Path(att.name).suffix.lower() in IMAGE_EXT
                          and att.size_kb < min_image_kb)


def process(messages: Iterable[Message], cfg: dict, root: Path, dry_run: bool = False) -> dict:
    clf = Classifier(cfg)
    store = Store(root, dry_run)
    run = datetime.now().isoformat(timespec="seconds")
    rows: list[dict] = []
    counts = Counter()
    for msg in messages:
        counts["messages scanned"] += 1
        if not sent_to_target(msg, cfg.get("target_recipients") or []):
            counts["skipped: not sent to a target address"] += 1
            continue
        if not msg.attachments:
            counts["skipped: no attachment"] += 1
            continue
        counts["messages processed"] += 1
        for att in msg.attachments:
            base = {"run": run, "received": msg.received.isoformat(timespec="minutes"),
                    "sender": msg.sender_email, "subject": msg.subject, "attachment": att.name}
            if is_decoration(att, cfg["min_image_kb"]):
                counts["attachments skipped: inline or small image"] += 1
                rows.append(base | {"country": "", "data_type": "", "confidence": "",
                                    "reason": "inline or small image (signature, logo)",
                                    "sha256": "", "status": "skipped", "saved_to": ""})
                continue
            d = clf.decide(msg, att.name)
            status, saved_to, digest = store.save(att.data, att.name, d.country, d.data_type,
                                                  cfg.get("extract_zips", False))
            counts[f"attachments {status}"] += 1
            rows.append(base | {"country": d.country, "data_type": d.data_type,
                                "confidence": d.confidence, "reason": d.reason,
                                "sha256": digest, "status": status, "saved_to": saved_to})
    store.log(rows)
    return {"rows": rows, "counts": counts, "run": run, "root": root, "dry_run": dry_run}
