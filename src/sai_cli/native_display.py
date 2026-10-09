"""Small terminal primitives for the site's traditional fixed-column helpers."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import TextIO


_SGR = re.compile(r"\x1b\[[0-9;]*m")
_COLORS = {"heading": "95", "free": "92", "allocated": "94", "blocked": "91", "unknown": "93", "bold": "1"}


def use_color(output: TextIO, environ: Mapping[str, str]) -> bool:
    return output.isatty() and "NO_COLOR" not in environ and environ.get("TERM") != "dumb"


def paint(text: str, role: str, enabled: bool) -> str:
    return f"\x1b[{_COLORS[role]}m{text}\x1b[0m" if enabled else text


def cell_width(text: str) -> int:
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
               for char in _SGR.sub("", text))


def row(cells: Iterable[str], widths: Iterable[int], *, gap: int = 2) -> str:
    return (" " * gap).join(cell + " " * max(0, width - cell_width(cell))
                            for cell, width in zip(cells, widths, strict=True)).rstrip()


def clip(text: str, width: int) -> str:
    if cell_width(text) <= width:
        return text
    result = ""
    for char in text:
        if cell_width(result + char) > width - 1:
            break
        result += char
    return result + "…"


def quantity(value: int | None) -> str:
    return "?" if value is None else str(value)


def allocation_bar(total: int | None, allocated: int | None, free: int | None, *, cells: int, color: bool,
                   unit_cells: bool = False) -> str:
    if total is None or allocated is None or free is None or total < allocated + free or total <= 0:
        return "?" if total != 0 else "-"
    if unit_cells and total > cells:
        return " ".join(paint(f"{symbol}×{amount}", role, color) for symbol, amount, role in
                        (("[#]", allocated, "allocated"), ("[x]", total - allocated - free, "blocked"), ("[_]", free, "free"))
                        if amount)
    count = total if unit_cells else cells
    busy = (allocated * count + total // 2) // total
    unavailable = ((total - free) * count + total // 2) // total
    blocked, idle = unavailable - busy, count - unavailable
    symbols = ("[#]", "[x]", "[_]") if unit_cells else ("#", "x", ".")
    bar = "".join(paint(symbol * amount, role, color) for symbol, amount, role in
                  zip(symbols, (busy, blocked, idle), ("allocated", "blocked", "free"), strict=True) if amount)
    return bar if unit_cells else "[" + bar + "]"
