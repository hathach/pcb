#!/usr/bin/env python3
"""Align markdown table columns in-place: pad cells so pipes line up in the source.

Usage: align_md_tables.py FILE [FILE ...]
Honors :--- / ---: / :--: alignment markers; leaves non-table text untouched.
"""
import re
import sys


def is_sep_cell(c):
    return re.fullmatch(r':?-+:?', c.strip()) is not None


def split_row(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    return [c.strip() for c in s.split('|')]


def align_block(rows):
    grid = [split_row(r) for r in rows]
    ncol = max(len(r) for r in grid)
    grid = [r + [''] * (ncol - len(r)) for r in grid]

    sep_idx = next((i for i, r in enumerate(grid)
                    if len(rows) > 1 and all(is_sep_cell(c) for c in r)), None)
    if sep_idx is None:                     # not a real table; leave as-is
        return rows

    aligns = ['l'] * ncol
    for j, c in enumerate(grid[sep_idx]):
        c = c.strip()
        l, r = c.startswith(':'), c.endswith(':')
        aligns[j] = 'c' if (l and r) else 'r' if r else 'l'

    width = [0] * ncol
    for i, r in enumerate(grid):
        if i == sep_idx:
            continue
        for j, c in enumerate(r):
            width[j] = max(width[j], len(c))
    width = [max(w, 3) for w in width]

    out = []
    for i, r in enumerate(grid):
        cells = []
        for j in range(ncol):
            w, a = width[j], aligns[j]
            if i == sep_idx:
                cells.append(':' + '-' * (w - 2) + ':' if a == 'c'
                             else '-' * (w - 1) + ':' if a == 'r'
                             else ':' + '-' * (w - 1) if a == 'l' and grid[sep_idx][j].strip().startswith(':')
                             else '-' * w)
            else:
                c = r[j]
                cells.append(c.rjust(w) if a == 'r' else c.center(w) if a == 'c' else c.ljust(w))
        out.append('| ' + ' | '.join(cells) + ' |')
    return out


def process(text):
    lines = text.split('\n')
    out, i = [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith('|'):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith('|'):
                j += 1
            out.extend(align_block(lines[i:j]))
            i = j
        else:
            out.append(lines[i])
            i += 1
    return '\n'.join(out)


if __name__ == '__main__':
    for path in sys.argv[1:]:
        with open(path, encoding='utf-8') as f:
            src = f.read()
        new = process(src)
        if new != src:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new)
            print(f'aligned tables in {path}')
        else:
            print(f'no change: {path}')
