#!/usr/bin/env python3
"""Export a person research plan's Source index to a sibling sources.csv.

Uses only the standard library. No network access or model calls.
The Markdown index remains authoritative; regenerate after changing it.
"""

import argparse
import csv
import io
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


FIELDS = ('source_id', 'title', 'url', 'publication_info', 'reading_note', 'support_note')


def table_cells(line):
    """Split a Markdown table row without splitting escaped pipes."""
    value = line.strip()
    if not (value.startswith('|') and value.endswith('|')):
        raise ValueError('Source index rows must start and end with |.')
    cells, cell, escaped = [], [], False
    for char in value[1:-1]:
        if char == '|' and not escaped:
            cells.append(''.join(cell).strip().replace(r'\|', '|'))
            cell = []
        else:
            cell.append(char)
        escaped = char == '\\' and not escaped
    cells.append(''.join(cell).strip().replace(r'\|', '|'))
    return cells


def parse_sources(markdown):
    headings = list(re.finditer(
        r'^##[ \t]+(?:\d+\.[ \t]*)?Source index[ \t]*#*[ \t]*$',
        markdown, re.M | re.I,
    ))
    if len(headings) != 1:
        raise ValueError('Expected exactly one Source index section.')
    body = markdown[headings[0].end():]
    end = re.search(r'^#{1,2}[ \t]+', body, re.M)
    if end:
        body = body[:end.start()]
    table = [table_cells(line) for line in body.splitlines() if line.lstrip().startswith('|')]
    if (len(table) < 2 or len(table[0]) != 5 or table[0][0].casefold() != 'source id'
            or len(table[1]) != 5 or not all(re.fullmatch(r':?-{3,}:?', c) for c in table[1])):
        raise ValueError('Expected the template’s five-column Source index table.')
    rows, seen = [], set()
    for number, cells in enumerate(table[2:], 1):
        if len(cells) != 5:
            raise ValueError(f'Source row {number} has {len(cells)} columns; expected 5.')
        source_id, link, publication, reading, support = cells
        if not re.fullmatch(r'SRC-?\d+', source_id):
            raise ValueError(f'Invalid source ID: {source_id!r}.')
        if source_id in seen:
            raise ValueError(f'Duplicate source ID: {source_id}.')
        seen.add(source_id)
        # One inline link per source; URLs may contain balanced parentheses.
        match = re.fullmatch(r'\[((?:\\.|[^\]\\])+)\]\((?:<([^>\n]+)>|(\S+))\)', link)
        if not match:
            raise ValueError(f'{source_id}: use one Markdown [title](URL) link in the title column.')
        title = re.sub(r'\\([\\`*{}\[\]()#+\-.!_|<>])', r'\1', match[1])
        url = match[2] or match[3]
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError(f'{source_id}: source URL must use http or https.')
        rows.append(dict(zip(FIELDS, (source_id, title, url, publication, reading, support))))
    return rows


def export_sources(plan_path, *, check=False):
    plan_path = Path(plan_path)
    if plan_path.name != 'research-plan.md':
        raise ValueError('Pass the person’s research-plan.md file.')
    rows = parse_sources(plan_path.read_text(encoding='utf-8-sig'))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    expected = stream.getvalue().encode('utf-8')
    output = plan_path.with_name('sources.csv')
    if check:
        if not output.exists() or output.read_bytes() != expected:
            raise ValueError('sources.csv is missing or stale; regenerate it from research-plan.md.')
    else:
        # Validate the whole input before atomically replacing a prior export.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.sources-', delete=False) as f:
                temporary = Path(f.name)
                f.write(expected)
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('research_plan', type=Path)
    parser.add_argument('--check', action='store_true', help='Check the export without writing files.')
    args = parser.parse_args()
    try:
        count = export_sources(args.research_plan, check=args.check)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')
    print(f'{"Checked" if args.check else "Exported"} {count} sources: {args.research_plan.with_name("sources.csv")}')


if __name__ == '__main__':
    main()
