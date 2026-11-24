"""Source-independent message and attachment records."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Attachment:
    name: str
    data: bytes
    inline: bool = False          # embedded in the body (signature logos, pasted images)

    @property
    def size_kb(self) -> float:
        return len(self.data) / 1024


@dataclass
class Message:
    id: str
    subject: str
    body: str
    sender_name: str
    sender_email: str
    recipients: list[str]
    received: datetime
    attachments: list[Attachment] = field(default_factory=list)
