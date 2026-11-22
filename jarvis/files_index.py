"""Ask my files: JARVIS reads the owner's notes, slides and PDFs into a private search index on the laptop.

Folders: JARVIS_STUDY_FOLDERS (separated by ;) or, by default, Documents, OneDrive\\Documents, Desktop and Downloads.
Reads .pdf .docx .pptx .txt .md .csv. Re-indexes changed files every few hours. Nothing leaves the laptop until an
agent quotes a passage in an answer.
"""
from __future__ import annotations

import os
import re
import threading
import zipfile
from pathlib import Path

from .guard import blocked

EXTS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".csv"}
MAX_FILE_MB = 60
MAX_FILES = 4000
CHUNK = 1200
SKIP_DIRS = {"node_modules", ".git", "AppData", "$RECYCLE.BIN", "__pycache__", ".venv", "venv", "site-packages"}
_lock = threading.Lock()


def folders() -> list[Path]:
    custom = os.environ.get("JARVIS_STUDY_FOLDERS", "").strip()
    if custom:
        return [Path(p.strip()).expanduser() for p in custom.split(";") if p.strip()]
    home = Path.home()
    cands = [home / "Documents", home / "OneDrive" / "Documents", home / "OneDrive" / "Desktop", home / "Desktop",
             home / "Downloads", home / "JARVIS"]
    return [c for c in cands if c.exists()]


def _xml_text(xml: str) -> str:
    xml = re.sub(r"</w:p>|</a:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def extract(path: Path) -> list[tuple[str, str]]:
    """[(page label, text), ...]"""
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return [(f"p{i + 1}", (pg.extract_text() or "")) for i, pg in enumerate(reader.pages[:400])]
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            return [("", _xml_text(z.read("word/document.xml").decode("utf-8", "ignore")))]
    if ext == ".pptx":
        with zipfile.ZipFile(path) as z:
            slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                            key=lambda n: int(re.findall(r"\d+", n)[-1]))
            return [(f"slide {int(re.findall(r'[0-9]+', n)[-1])}", _xml_text(z.read(n).decode("utf-8", "ignore")))
                    for n in slides]
    return [("", path.read_text(encoding="utf-8", errors="ignore")[:2_000_000])]


def _chunks(pages: list[tuple[str, str]]):
    for label, text in pages:
        text = re.sub(r"[ \t]+", " ", text).strip()
        for i in range(0, len(text), CHUNK):
            piece = text[i:i + CHUNK + 150]
            if piece.strip():
                yield label, piece


def index(store, limit_seconds: float = 600) -> dict:
    """Index new and changed files. Safe to call often."""
    import time
    if not _lock.acquire(blocking=False):
        return {"indexed": 0, "note": "already indexing"}
    t0 = time.monotonic()
    done = seen = 0
    try:
        known = {r["path"]: r["mtime"] for r in store.query("SELECT path, mtime FROM file_index")}
        alive = set()
        for root in folders():
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                for fn in filenames:
                    p = Path(dirpath) / fn
                    if p.suffix.lower() not in EXTS or fn.startswith("~$") or blocked(fn):
                        continue
                    seen += 1
                    if seen > MAX_FILES:
                        break
                    key = str(p)
                    alive.add(key)
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    if st.st_size > MAX_FILE_MB * 1e6 or known.get(key) == st.st_mtime:
                        continue
                    if time.monotonic() - t0 > limit_seconds:
                        return {"indexed": done, "note": "time's up for this round; continues later"}
                    try:
                        pieces = list(_chunks(extract(p)))
                    except Exception:  # noqa: BLE001 - unreadable or password-protected file
                        pieces = []
                    store.execute("DELETE FROM file_chunks WHERE path = ?", (key,))
                    for label, body in pieces[:3000]:
                        store.execute("INSERT INTO file_chunks (path, name, page, body) VALUES (?,?,?,?)",
                                      (key, p.name, label, body))
                    store.execute("INSERT OR REPLACE INTO file_index (path, mtime, chunks) VALUES (?,?,?)",
                                  (key, st.st_mtime, len(pieces)))
                    done += 1
        for gone in set(known) - alive:
            store.execute("DELETE FROM file_chunks WHERE path = ?", (gone,))
            store.execute("DELETE FROM file_index WHERE path = ?", (gone,))
        return {"indexed": done, "files_known": len(alive)}
    finally:
        _lock.release()


def search(store, query: str, limit: int = 8) -> list[dict]:
    words = [w for w in re.findall(r"[A-Za-z0-9]{2,}", query)]
    if not words:
        return []
    if getattr(store, "fts", False):
        q = " OR ".join(f'"{w}"' for w in words)
        rows = store.query("SELECT path, name, page, snippet(file_chunks, 3, '**', '**', ' … ', 40) AS excerpt, "
                           "bm25(file_chunks) AS score FROM file_chunks WHERE file_chunks MATCH ? "
                           "ORDER BY score LIMIT ?", (q, limit))
    else:
        rows = store.query("SELECT path, name, page, substr(body, 1, 400) AS excerpt FROM file_chunks "
                           "WHERE body LIKE ? LIMIT ?", (f"%{words[0]}%", limit))
    return [{"file": r["name"], "where": r["page"], "path": r["path"], "excerpt": r["excerpt"]} for r in rows]
