"""Page-spec parser: "1,3-5,8" (1-indexed) -> sorted zero-indexed list."""

from __future__ import annotations


def parse_pagespec(spec: str | None, page_count: int) -> list[int]:
    """Parse a page spec into zero-indexed page numbers.

    Args:
        spec: e.g. "1,3-5,8". None/"" means all pages.
        page_count: total pages in doc (for validation/clamping).

    Returns:
        Sorted unique zero-indexed page indices.

    Raises:
        ValueError on bad syntax or out-of-range pages.
    """
    if spec is None or str(spec).strip() == "":
        return list(range(page_count))
    pages: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a.strip()), int(b.strip())
            except ValueError:
                raise ValueError(f"Bad page range: {part!r}")
            if start < 1 or end < 1 or start > page_count or end > page_count:
                raise ValueError(f"Page range {part!r} out of range (1-{page_count})")
            if start > end:
                start, end = end, start
            pages.update(range(start - 1, end))
        else:
            try:
                n = int(part)
            except ValueError:
                raise ValueError(f"Bad page number: {part!r}")
            if n < 1 or n > page_count:
                raise ValueError(f"Page {n} out of range (1-{page_count})")
            pages.add(n - 1)
    if not pages:
        raise ValueError("Empty page spec")
    return sorted(pages)


def parse_order(spec: str, page_count: int) -> list[int]:
    """Parse an explicit page order, preserving it exactly.

    Unlike :func:`parse_pagespec` (which sorts and de-duplicates), this is for
    reordering: ``"3,1,2"`` -> ``[2, 0, 1]`` and ``"5-3"`` -> ``[4, 3, 2]``.
    A subset is allowed — only the listed pages are kept, in that order.

    Raises:
        ValueError on bad syntax or out-of-range pages.
    """
    if spec is None or str(spec).strip() == "":
        raise ValueError("Empty page order")
    order: list[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a.strip()), int(b.strip())
            except ValueError:
                raise ValueError(f"Bad page range: {part!r}")
            step = 1 if start <= end else -1
            order.extend(range(start - 1, end - 1 + step, step))
        else:
            try:
                order.append(int(part) - 1)
            except ValueError:
                raise ValueError(f"Bad page number: {part!r}")
    if not order:
        raise ValueError("Empty page order")
    for p in order:
        if p < 0 or p >= page_count:
            raise ValueError(f"Page {p + 1} out of range (1-{page_count})")
    return order


def parse_ranges_for_split(spec: str | None, page_count: int) -> list[list[int]]:
    """Parse split spec into groups. "1-2,3-5" -> [[0,1],[2,3,4]]."""
    if spec is None or str(spec).strip() == "":
        return [[i] for i in range(page_count)]
    groups: list[list[int]] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a.strip()), int(b.strip())
            if start > end:
                start, end = end, start
            groups.append(list(range(start - 1, end)))
        else:
            groups.append([int(part) - 1])
    for g in groups:
        for p in g:
            if p < 0 or p >= page_count:
                raise ValueError(f"Page {p + 1} out of range (1-{page_count})")
    return groups
