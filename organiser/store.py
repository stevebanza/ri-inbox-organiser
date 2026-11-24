"""Saving files: country/type folders, content de-duplication, safe zip extraction and a
manifest that records every decision."""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

MANIFEST_COLUMNS = ["run", "received", "sender", "subject", "attachment", "country",
                    "data_type", "confidence", "reason", "sha256", "status", "saved_to"]
BAD_CHARS = '<>:"/\\|?*'


def safe_filename(name: str) -> str:
    cleaned = "".join("_" if c in BAD_CHARS or ord(c) < 32 else c for c in name).strip(" .")
    return cleaned or "attachment"


def unique_path(folder: Path, filename: str) -> Path:
    safe = Path(safe_filename(filename))
    path = folder / safe.name
    n = 1
    while path.exists():  # numbered copies are built from the cleaned name too
        path = folder / f"{safe.stem}_{n}{safe.suffix}"
        n += 1
    return path


class Store:
    def __init__(self, root: Path, dry_run: bool = False):
        self.root = Path(root)
        self.dry_run = dry_run
        self.manifest = self.root / "_manifest.csv"
        self.known: dict[str, str] = {}
        if self.manifest.exists():
            with self.manifest.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["status"] == "saved":
                        self.known[r["sha256"]] = r["saved_to"]

    def save(self, data: bytes, filename: str, country: str, data_type: str,
             extract_zips: bool) -> tuple[str, str, str]:
        """Return (status, saved_to, sha256). Status: saved | duplicate | would save."""
        digest = hashlib.sha256(data).hexdigest()
        if digest in self.known:
            return "duplicate", self.known[digest], digest
        folder = self.root / country / data_type
        path = unique_path(folder, filename)
        rel = str(path.relative_to(self.root))
        if self.dry_run:
            self.known[digest] = rel
            return "would save", rel, digest
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if extract_zips and path.suffix.lower() == ".zip":
            self._extract(data, path.with_suffix(""))
        self.known[digest] = rel
        return "saved", rel, digest

    @staticmethod
    def _extract(data: bytes, target: Path) -> None:
        """Unzip next to the archive, refusing any member that would land outside it."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            return
        base = target.resolve()
        for member in zf.infolist():
            dest = (target / member.filename).resolve()
            if not dest.is_relative_to(base) or member.is_dir():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))

    def log(self, rows: list[dict]) -> None:
        if self.dry_run or not rows:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        new = not self.manifest.exists()
        with self.manifest.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
            if new:
                w.writeheader()
            w.writerows(rows)
