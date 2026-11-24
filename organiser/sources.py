"""Where messages come from: Outlook desktop (Windows) or a folder of .eml files."""
from __future__ import annotations

import email
import email.policy
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

from .models import Attachment, Message


# ---------------------------------------------------------------- .eml folder
def eml_messages(folder: Path, days_back: int | None = None,
                 now: datetime | None = None) -> Iterator[Message]:
    """Read every .eml file in `folder` (exported mail, or the demo inbox)."""
    cutoff = (now or datetime.now()) - timedelta(days=days_back) if days_back else None
    for path in sorted(Path(folder).glob("*.eml")):
        msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
        received = parsedate_to_datetime(msg["Date"]).replace(tzinfo=None) if msg["Date"] \
            else datetime.fromtimestamp(path.stat().st_mtime)
        if cutoff and received < cutoff:
            continue
        body_part = msg.get_body(preferencelist=("plain", "html"))
        body = body_part.get_content() if body_part else ""
        attachments = []
        for part in msg.walk():
            name = part.get_filename()
            if not name:
                continue
            inline = part.get_content_disposition() == "inline" or bool(part["Content-ID"])
            attachments.append(Attachment(name, part.get_payload(decode=True) or b"", inline))
        sender_name, sender_email = parseaddr(msg["From"] or "")
        recipients = [a for _, a in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []))]
        yield Message(id=msg["Message-ID"] or path.name, subject=msg["Subject"] or "",
                      body=body, sender_name=sender_name, sender_email=sender_email.lower(),
                      recipients=[r.lower() for r in recipients], received=received,
                      attachments=attachments)


# ---------------------------------------------------------------- Outlook
OL_FOLDER_INBOX, OL_MAIL_ITEM = 6, 43
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"


def _smtp(recipient) -> str:
    """Best-effort SMTP address for an Outlook recipient (Exchange users and lists)."""
    entry = getattr(recipient, "AddressEntry", None)
    for getter in ("GetExchangeUser", "GetExchangeDistributionList"):
        try:
            obj = getattr(entry, getter)()
            if obj and obj.PrimarySmtpAddress:
                return str(obj.PrimarySmtpAddress)
        except Exception:  # noqa: BLE001 - COM raises many error types
            pass
    for holder in (entry, recipient):
        try:
            value = holder.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS)
            if value:
                return str(value)
        except Exception:  # noqa: BLE001
            pass
    return str(getattr(recipient, "Address", "") or "")


def outlook_messages(days_back: int, folder_path: str | None = None) -> Iterator[Message]:
    """Read the Outlook desktop inbox (or a subfolder such as 'Inbox/RI data'), newest first.

    Needs Windows, Outlook and pywin32 (`pip install pywin32`)."""
    import win32com.client  # noqa: PLC0415 - Windows only

    ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    folder = ns.GetDefaultFolder(OL_FOLDER_INBOX)
    for part in (folder_path or "").split("/")[1:]:
        folder = folder.Folders[part]
    items = folder.Items
    items.Sort("[ReceivedTime]", True)
    cutoff = datetime.now() - timedelta(days=days_back)
    tmp = Path(tempfile.mkdtemp(prefix="ri_inbox_"))
    for item in items:
        if getattr(item, "Class", None) != OL_MAIL_ITEM:
            continue
        rt = item.ReceivedTime
        received = datetime(rt.year, rt.month, rt.day, rt.hour, rt.minute, rt.second)
        if received < cutoff:
            break  # sorted newest first
        attachments = []
        for i in range(1, item.Attachments.Count + 1):
            att = item.Attachments.Item(i)
            path = tmp / f"{i}_{att.FileName}"
            att.SaveAsFile(str(path))
            try:
                cid = att.PropertyAccessor.GetProperty(PR_ATTACH_CONTENT_ID)
            except Exception:  # noqa: BLE001
                cid = ""
            attachments.append(Attachment(att.FileName, path.read_bytes(), inline=bool(cid)))
            path.unlink(missing_ok=True)
        recipients = [_smtp(item.Recipients.Item(i)).lower()
                      for i in range(1, item.Recipients.Count + 1)]
        yield Message(id=item.EntryID, subject=item.Subject or "", body=item.Body or "",
                      sender_name=item.SenderName or "",
                      sender_email=(item.SenderEmailAddress or "").lower(),
                      recipients=recipients, received=received, attachments=attachments)
