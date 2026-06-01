#!/usr/bin/env python3
"""Append to and compact Tomorrowland's shared Markdown memory.

Shared memory lives in ``docs/memory/*.md`` as newest-first, dated entries.
This helper keeps the on-disk format consistent and stops the *active* files
from growing past the point where an agent can read them, by moving stale
``Done``/``Superseded`` entries into a sibling ``archive/`` file (still in git,
just out of the agent read path).

Subcommands
-----------
append   Insert a new entry at the top (just under the file intro), in the
         canonical format. The entry body is read from stdin.
archive  Move old ``Done``/``Superseded`` entries out of an active file into
         ``docs/memory/archive/<name>.md``. ``Active``/``Watch`` entries are
         never archived. Default policy: archive Done/Superseded entries that
         fall outside the newest ``--keep`` (25) entries.
stats    Print line counts and per-status entry counts so you can tell when a
         file is due for archiving.

Examples
--------
    printf '**Done:** merged.\\n**Next:** ...\\n' | \\
        python memory.py append --file handoffs \\
            --title "review+fix #624" --status Done --source "PR #624, cec926d"

    python memory.py stats
    python memory.py archive --file current-state --keep 25 --dry-run
    python memory.py archive --file current-state            # apply
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_KNOWN = ("current-state", "decisions", "handoffs", "glossary")
_STATUSES = ("Active", "Superseded", "Done", "Watch")
_HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b")
_STATUS_RE = re.compile(r"^Status:\s*([A-Za-z]+)", re.MULTILINE)


def _memory_dir(arg: str | None) -> Path:
    """Resolve the docs/memory directory (search upward from cwd by default)."""
    if arg:
        return Path(arg)
    cur = Path.cwd()
    for p in (cur, *cur.parents):
        if (p / "docs" / "memory").is_dir():
            return p / "docs" / "memory"
    return Path("docs/memory")


def _resolve(file_arg: str, mem_dir: Path) -> Path:
    if file_arg.endswith(".md") or "/" in file_arg:
        return Path(file_arg)
    return mem_dir / f"{file_arg}.md"


def _split(text: str) -> tuple[str, list[str]]:
    """Split *text* into (intro, [entry_blocks]).

    An entry block starts at a ``## `` header and runs up to the next ``## ``
    header (its trailing ``---`` / blank lines stay attached to the block), so
    blocks are self-contained and can be moved or dropped without reflowing the
    rest of the file.
    """
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), None)
    if start is None:
        return text, []
    intro = "".join(lines[:start])
    blocks: list[str] = []
    cur: list[str] = []
    for ln in lines[start:]:
        if ln.startswith("## ") and cur:
            blocks.append("".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        blocks.append("".join(cur))
    return intro, blocks


def _entry_date(block: str) -> date | None:
    m = _HEADER_RE.match(block)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _entry_status(block: str) -> str | None:
    m = _STATUS_RE.search(block)
    return m.group(1).capitalize() if m else None


def cmd_append(args: argparse.Namespace) -> int:
    path = _resolve(args.file, _memory_dir(args.memory_dir))
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    body = sys.stdin.read().strip()
    if not body:
        print("error: entry body is empty — pipe it on stdin", file=sys.stderr)
        return 1
    d = args.date or date.today().isoformat()
    meta = f"Status: {args.status}"
    if args.source:
        meta += f"\nSource: {args.source}"
    entry = f"## {d} — {args.title}\n\n{meta}\n\n{body}\n"

    intro, blocks = _split(path.read_text(encoding="utf-8"))
    sep = "\n---\n\n" if blocks else "\n"
    new = intro.rstrip("\n") + "\n\n" + entry + sep + "".join(blocks)
    path.write_text(new.rstrip("\n") + "\n", encoding="utf-8")
    print(f"appended to {path.name}: {d} — {args.title} [{args.status}]")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    mem = _memory_dir(args.memory_dir)
    path = _resolve(args.file, mem)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    statuses = {s.capitalize() for s in (args.status or ["Done", "Superseded"])}
    cutoff = date.today() - timedelta(days=args.days) if args.days else None

    intro, blocks = _split(path.read_text(encoding="utf-8"))
    keep: list[str] = []
    move: list[str] = []
    for idx, b in enumerate(blocks):
        st = _entry_status(b)
        d = _entry_date(b)
        beyond_keep = idx >= args.keep
        too_old = cutoff is not None and d is not None and d < cutoff
        if st in statuses and (beyond_keep or too_old):
            move.append(b)
        else:
            keep.append(b)

    if not move:
        print(f"{path.name}: nothing to archive (keep={args.keep}, statuses={sorted(statuses)})")
        return 0

    arc_dir = mem / "archive"
    arc_path = arc_dir / path.name
    if arc_path.exists():
        arc_intro, arc_blocks = _split(arc_path.read_text(encoding="utf-8"))
    else:
        arc_intro = (
            f"# {path.stem} — archive\n\n"
            f"Archived (Done/Superseded) entries moved out of `docs/memory/{path.name}` to keep "
            f"the active file readable. History only — not in the agent read path.\n"
        )
        arc_blocks = []

    new_main = intro.rstrip("\n") + "\n\n" + "".join(keep)
    new_arc = arc_intro.rstrip("\n") + "\n\n" + "".join(move) + "".join(arc_blocks)

    verb = "(dry-run) would archive" if args.dry_run else "archived"
    if not args.dry_run:
        arc_dir.mkdir(exist_ok=True)
        path.write_text(new_main.rstrip("\n") + "\n", encoding="utf-8")
        arc_path.write_text(new_arc.rstrip("\n") + "\n", encoding="utf-8")
    n = len(move)
    print(
        f"{verb} {n} entr{'y' if n == 1 else 'ies'} from {path.name} "
        f"→ archive/{path.name}; {len(keep)} kept"
    )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    mem = _memory_dir(args.memory_dir)
    names = [args.file] if args.file else list(_KNOWN)
    for name in names:
        path = _resolve(name, mem)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        _, blocks = _split(text)
        by_status: dict[str, int] = {}
        for b in blocks:
            st = _entry_status(b) or "—"
            by_status[st] = by_status.get(st, 0) + 1
        counts = ", ".join(f"{k}:{v}" for k, v in sorted(by_status.items()))
        # Entry count is a better bloat signal than raw lines (entries vary in size).
        flag = "  <- consider: archive" if len(blocks) > 40 else ""
        nlines = text.count("\n") + 1
        print(f"{path.name:18} {nlines:5} lines  {len(blocks):3} entries  [{counts}]{flag}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="memory.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--memory-dir", help="docs/memory dir (default: search upward from cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append", help="add a new entry at the top of a memory file")
    ap.add_argument(
        "--file", required=True, help="current-state | decisions | handoffs | glossary | path"
    )
    ap.add_argument("--title", required=True, help="short entry title")
    ap.add_argument("--status", required=True, choices=list(_STATUSES))
    ap.add_argument("--source", default="", help="e.g. 'PR #624, commit cec926d'")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today)")
    ap.set_defaults(func=cmd_append)

    arc = sub.add_parser(
        "archive", help="move stale Done/Superseded entries to docs/memory/archive/"
    )
    arc.add_argument("--file", required=True)
    arc.add_argument(
        "--keep", type=int, default=25, help="always keep the newest N entries (default 25)"
    )
    arc.add_argument(
        "--days", type=int, default=0, help="also archive entries older than N days (0=off)"
    )
    arc.add_argument("--status", nargs="*", help="statuses to archive (default: Done Superseded)")
    arc.add_argument("--dry-run", action="store_true", help="report without writing")
    arc.set_defaults(func=cmd_archive)

    st = sub.add_parser("stats", help="show line/entry counts per file")
    st.add_argument("--file", default="", help="one file, or all known files if omitted")
    st.set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
