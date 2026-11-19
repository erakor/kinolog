"""Table output: Rich when installed, plain ASCII otherwise."""

from __future__ import annotations

try:
    import click
    from rich.console import Console
    from rich.table import Table

    USE_CLICK = True
    console = Console()
except ImportError:
    USE_CLICK = False
    console = None


def print_table(title: str, headers: list[str], rows: list[list[str]]):
    """Render a table with Rich if available, else plain ASCII."""
    if USE_CLICK and console:
        tbl = Table(title=title)
        for h in headers:
            tbl.add_column(h)
        for r in rows:
            tbl.add_row(*[str(x) for x in r])
        console.print(tbl)
    else:
        if not rows:
            print(f"\n=== {title} === (empty)\n")
            return
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(val)))
        sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
        print(f"\n=== {title} ===")
        print(sep)
        header_line = (
            "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
        )
        print(header_line)
        print(sep)
        for row in rows:
            line = (
                "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
            )
            print(line)
        print(sep + "\n")
