import re
from pathlib import Path

from .models import Chunk

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def load_document(path: str | Path) -> tuple[str, str]:
    text = Path(path).read_text(encoding="utf-8")
    return _title(text) or Path(path).stem, text


def _title(text: str) -> str | None:
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            return match.group(2).strip()
    return None


def _sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    title = ""
    buf: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            if buf:
                sections.append((title, "\n".join(buf).strip()))
                buf = []
            title = match.group(2).strip()
        else:
            buf.append(line)
    if buf:
        sections.append((title, "\n".join(buf).strip()))
    return [(title, body) for title, body in sections if body]


def _split(body: str, size: int, overlap: int) -> list[str]:
    body = body.strip()
    if len(body) <= size:
        return [body] if body else []
    pieces: list[str] = []
    start, length = 0, len(body)
    while start < length:
        end = min(start + size, length)
        if end < length:
            boundary = body.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        piece = body[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        start = end - overlap if end - overlap > start else end
    return pieces


def chunk_markdown(text: str, *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 0
    for section, body in _sections(text):
        for piece in _split(body, chunk_size, chunk_overlap):
            chunks.append(Chunk(section=section, ordinal=ordinal, text=piece))
            ordinal += 1
    return chunks
