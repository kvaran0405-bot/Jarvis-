"""A tiny PDF writer (no extra packages): enough for clean one- or two-page documents such as quotes."""
from __future__ import annotations

from pathlib import Path

PAGE_W, PAGE_H = 595, 842   # A4 in points
MARGIN = 50

# Helvetica widths (per 1000 em) for the characters we use most; others fall back to an average.
_W = {" ": 278, ",": 278, ".": 278, ":": 278, "-": 333, "(": 333, ")": 333, "/": 278, "$": 556, "%": 889,
      "&": 667, "@": 1015, "#": 556, "'": 191, "+": 584, "x": 500, "i": 222, "l": 222, "j": 222, "t": 278,
      "f": 278, "r": 333, "m": 833, "w": 722, "I": 278, "M": 833, "W": 944}


def text_width(text: str, size: float, bold: bool = False) -> float:
    w = 0
    for ch in text:
        if ch in _W:
            w += _W[ch]
        elif ch.isdigit():
            w += 556
        elif ch.isupper():
            w += 690
        else:
            w += 530
    return w * size / 1000 * (1.05 if bold else 1)


def _esc(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("•", "-")
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Doc:
    def __init__(self):
        self.pages: list[list[str]] = [[]]
        self.y = PAGE_H - MARGIN

    @property
    def ops(self) -> list[str]:
        return self.pages[-1]

    def new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def need(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.new_page()

    def text(self, x: float, y: float, text: str, size: float = 10, bold: bool = False,
             color: tuple = (0, 0, 0), align: str = "left", serif: bool = False) -> None:
        w = text_width(text, size, bold) * (.92 if serif else 1)
        if align == "right":
            x -= w
        elif align == "center":
            x -= w / 2
        r, g, b = color
        font = ("F4" if bold else "F3") if serif else ("F2" if bold else "F1")
        self.ops.append(f"BT {r} {g} {b} rg /{font} {size} Tf {x:.1f} {y:.1f} Td ({_esc(text)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 0.5, color: tuple = (0.8, 0.8, 0.8)) -> None:
        r, g, b = color
        self.ops.append(f"{r} {g} {b} RG {width} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def rect(self, x: float, y: float, w: float, h: float, color: tuple) -> None:
        r, g, b = color
        self.ops.append(f"{r} {g} {b} rg {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")

    def wrap(self, text: str, width: float, size: float = 10, bold: bool = False) -> list[str]:
        lines = []
        for para in text.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = f"{cur} {word}".strip()
                if cur and text_width(trial, size, bold) > width:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        return lines

    def paragraph(self, text: str, size: float = 10, bold: bool = False, x: float = MARGIN,
                  width: float = PAGE_W - 2 * MARGIN, color: tuple = (0, 0, 0), gap: float = 1.4,
                  serif: bool = False) -> None:
        for ln in self.wrap(text, width / (.92 if serif else 1), size, bold):
            self.need(size * gap)
            self.y -= size * gap
            self.text(x, self.y, ln, size, bold, color, serif=serif)

    def save(self, path: Path) -> Path:
        objs: list[bytes] = []
        n_pages = len(self.pages)
        # 1 catalog, 2 pages, 3-6 fonts (Helvetica, bold, Times, bold), then (page, content) pairs
        kids = " ".join(f"{7 + 2 * i} 0 R" for i in range(n_pages))
        objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman /Encoding /WinAnsiEncoding >>")
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold /Encoding /WinAnsiEncoding >>")
        for i, ops in enumerate(self.pages):
            stream = "\n".join(ops).encode("latin-1", "replace")
            objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                        f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >> /Contents {8 + 2 * i} 0 R >>".encode())
            objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for num, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(out))
        return path
