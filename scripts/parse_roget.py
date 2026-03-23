"""
parse_roget.py
Parse Roget's Thesaurus 1911 (Project Gutenberg E-Text #10681).
Extracts the four-level hierarchy and word lists per category.

Output: data/roget/roget_parsed.json

Schema:
{
  "meta": {
    "source": "Project Gutenberg E-Text #10681",
    "total_classes": 6,
    "total_sections": int,
    "total_categories": int,
    "total_raw_words": int,
    "parse_timestamp": "ISO8601"
  },
  "classes": [
    {
      "id": 1,
      "name": "Abstract Relations",
      "sections": [
        {
          "id": "1.1",
          "name": "Existence",
          "categories": [
            {
              "id": "1.1.1",
              "number": 1,
              "name": "Existence",
              "words": ["being", "entity", ...],
              "raw_line_start": int,
              "raw_line_end": int
            }
          ]
        }
      ]
    }
  ]
}

Notes:
- Extract single-word tokens only. Skip phrases (contains space after
  stripping) and tokens shorter than 2 characters.
- Preserve case from the source but also store a lowercased version.
- Do NOT filter obsolete terms here — that is the job of filter_vocab.py.
  Mark terms containing | or flagged with obsolete markers but keep them.
- Words appearing in multiple categories are kept in ALL categories.
  Multi-category membership is intentional (principled polysemy).
- The Gutenberg header and footer (before/after the thesaurus content)
  must be excluded. Detect by finding the start of Class I and the
  end-of-project marker.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROGET_FILE   = PROJECT_ROOT / "data" / "roget" / "roget1911.txt"
OUTPUT_FILE  = PROJECT_ROOT / "data" / "roget" / "roget_parsed.json"

# Known class names in order — used to validate parse completeness
EXPECTED_CLASSES = [
    "Abstract Relations",
    "Space",
    "Matter",
    "Intellect",
    "Volition",
    "Affections",
]


def parse_roget(text: str) -> dict:
    """
    Parse the full Roget's text into the hierarchy schema.

    Format observed in inspection:
    - CLASS I / CLASS II ... (one per line, body line ~0)
    - SECTION I.              (one per line)
    - EXISTENCE               (section name on the NEXT non-empty line after SECTION)
    - 1. BEING, IN THE ABSTRACT  (subsection heading — all caps, no N. marker)
    - 1. Existence \ufffd N. existence, being,...  (category — mixed case, \ufffd separator, N. on same line)
    - continuation lines (indented word list)
    - V. verb, verb; ...  (part-of-speech blocks)
    - Adj. adjective; ... (ditto)
    - Phr. phrase text.   (phrases — skip; the "no spaces" filter catches most)

    The separator between category name and N. is \ufffd (Unicode replacement
    char U+FFFD) because the original file uses a non-standard byte that
    Python's errors='replace' substitutes. We also accept \u2013 and \u2014
    for resilience.

    Some category names have bracketed prefixes, e.g.:
        10. [Want, or absence of relation.] Irrelation \ufffd N. irrelation,...
    """
    lines = text.splitlines()

    # ── Locate thesaurus body ─────────────────────────────────────────
    body_start = 0
    body_end   = len(lines)
    for i, line in enumerate(lines):
        if re.match(r'^CLASS\s+I\s*$', line.strip(), re.IGNORECASE):
            body_start = i
            break
    for i in range(len(lines) - 1, -1, -1):
        if 'END OF THE PROJECT GUTENBERG' in lines[i].upper():
            body_end = i
            break

    body = lines[body_start:body_end]

    # ── Patterns ──────────────────────────────────────────────────────
    # CLASS I … CLASS VI (exactly at line start, short line)
    CLASS_PAT = re.compile(r'^CLASS\s+(I{1,3}V?|VI?)\s*$', re.IGNORECASE)

    # SECTION I. header line (the section NAME follows on the next non-empty line)
    SECTION_HDR_PAT = re.compile(r'^SECTION\s+[IVXLC]+\.?\s*$', re.IGNORECASE)

    # Category line: number + optional [bracketed note] + mixed-case name +
    # separator (\ufffd / em-dash) + N. + rest of word list on same line.
    # The separator is the key differentiator from subsection headings.
    CAT_PAT = re.compile(
        r'^(\d{1,4})\.\s+'            # category number
        r'(.+?)'                       # name (non-greedy, may include [brackets])
        r'\s*[\u2013\u2014\ufffd]+\s*' # separator: en-dash, em-dash, or \ufffd
        r'N\.\s*(.*)'                  # N. marker + rest of word list
    )

    # Subsection heading: number + ALL-CAPS label (no N. separator)
    # e.g. "1. BEING, IN THE ABSTRACT"
    SUBSEC_PAT = re.compile(r'^\d{1,4}\.\s+[A-Z][A-Z,\s\-/]+$')

    # Part-of-speech block marker at line start
    POS_PAT = re.compile(r'^(N|V|Adj|Adv|Phr)\.\s+(.*)')

    # ── State ─────────────────────────────────────────────────────────
    classes:   list[dict] = []
    cur_class:   dict | None = None
    cur_section: dict | None = None
    cur_cat:     dict | None = None
    class_count      = 0
    section_counter  = 0
    cat_counter      = 0
    awaiting_section_name = False
    in_phrase_block       = False

    # ── Word extraction helpers ───────────────────────────────────────

    # Obsolete/archaic marker characters used in this Gutenberg file:
    #   \u2020  † dagger       — primary obsolete marker
    #   \u2021  ‡ double-dag   — more archaic variant
    #   \u2014  — em-dash      — alternative marker / separator
    #   \u2013  – en-dash      — variant
    #   \ufffd    replacement  — non-UTF-8 byte in some copies
    #   \xa0    nbsp           — non-breaking space after markers
    _MARKERS = '\u2020\u2021\u2014\u2013\ufffd\xa0'
    _PUNCT   = r'[\s.,:;!?()\[\]{}\'"]*'

    def clean_token(tok: str) -> str:
        """Strip obsolete markers and surrounding punctuation from a token.

        Order matters:
          1. strip whitespace
          2. strip surrounding punctuation  (may expose trailing †)
          3. strip trailing obsolete markers (now reachable)
          4. final whitespace strip
        """
        tok = tok.strip()
        tok = re.sub(r'^' + _PUNCT, '', tok)
        tok = re.sub(_PUNCT + r'$', '', tok)
        tok = tok.rstrip(_MARKERS)
        tok = tok.lstrip(_MARKERS)   # catch leading markers too
        return tok.strip()

    def extract_words(chunk: str) -> list[str]:
        """Extract single-word tokens from a thesaurus word-list chunk."""
        # Normalize non-breaking spaces (\xa0) to regular spaces before splitting
        chunk = chunk.replace('\xa0', ' ')
        # Remove [bracketed annotations] e.g. [Lat.], [obs.], [arch.]
        chunk = re.sub(r'\[[^\]]*\]', '', chunk)
        # Remove (parenthetical notes)
        chunk = re.sub(r'\([^)]*\)', '', chunk)
        # Remove &c cross-references (etcetera + anything before next separator)
        chunk = re.sub(r'&c[^,;]*', '', chunk)

        words = []
        for tok in re.split(r'[,;]+', chunk):
            tok = clean_token(tok)
            if not tok:
                continue
            # Single word only — phrases are excluded
            if ' ' in tok or '\t' in tok:
                continue
            # Minimum useful length
            if len(tok) < 2:
                continue
            # Skip pure numbers (cross-reference IDs like "494", "151")
            if re.match(r'^\d+$', tok):
                continue
            # Skip &c fragments and tokens starting with digits
            if tok.startswith('&') or re.match(r'^\d', tok):
                continue
            words.append(tok)
        return words

    # ── Main parse loop ───────────────────────────────────────────────
    for line_no, line in enumerate(body):
        stripped = line.strip()

        # Section name comes on the next non-empty line after SECTION I.
        if awaiting_section_name:
            if stripped:
                cur_section['name'] = stripped  # type: ignore[index]
                awaiting_section_name = False
            continue  # consume the line whether blank or not

        if not stripped:
            continue

        # ── CLASS ─────────────────────────────────────────────────────
        if CLASS_PAT.match(stripped):
            class_count += 1
            cur_class = {
                'id':   class_count,
                'name': EXPECTED_CLASSES[class_count - 1]
                        if class_count <= 6 else f'Class {class_count}',
                'sections': [],
            }
            classes.append(cur_class)
            cur_section = None
            cur_cat     = None
            in_phrase_block = False
            continue

        if not cur_class:
            continue

        # ── SECTION header ────────────────────────────────────────────
        if SECTION_HDR_PAT.match(stripped):
            section_counter += 1
            cur_section = {
                'id':         f'{cur_class["id"]}.{len(cur_class["sections"]) + 1}',
                'name':       '',   # filled by next non-empty line
                'categories': [],
            }
            cur_class['sections'].append(cur_section)
            cur_cat         = None
            in_phrase_block = False
            awaiting_section_name = True
            continue

        # ── CATEGORY ──────────────────────────────────────────────────
        m = CAT_PAT.match(stripped)
        if m:
            # Ensure a section exists (handles categories before any SECTION)
            if cur_section is None:
                cur_section = {
                    'id':         f'{cur_class["id"]}.0',
                    'name':       'General',
                    'categories': [],
                }
                cur_class['sections'].append(cur_section)

            cat_counter += 1
            name = m.group(2).strip()
            # Strip leading [bracketed description] if present
            # e.g. "[Want, or absence of relation.] Irrelation" → "Irrelation"
            name = re.sub(r'^\[[^\]]*\]\s*', '', name).strip()

            cur_cat = {
                'id':             f'{cur_section["id"]}.{len(cur_section["categories"]) + 1}',
                'number':         int(m.group(1)),
                'name':           name,
                'words':          [],
                'raw_line_start': line_no,
                'raw_line_end':   line_no,
            }
            cur_section['categories'].append(cur_cat)
            in_phrase_block = False
            # Extract words from the rest of the category's opening line
            cur_cat['words'].extend(extract_words(m.group(3)))
            continue

        # ── SUBSECTION heading (all caps, no N. marker) ───────────────
        # e.g. "1. BEING, IN THE ABSTRACT"
        # Reset cur_cat so stray prose lines between cats aren't harvested.
        if SUBSEC_PAT.match(stripped):
            cur_cat         = None
            in_phrase_block = False
            continue

        # ── Word extraction within current category body ──────────────
        if cur_cat is not None:
            cur_cat['raw_line_end'] = line_no

            pos_m = POS_PAT.match(stripped)
            if pos_m:
                pos = pos_m.group(1)
                if pos == 'Phr':
                    # Phrase block — the "no spaces" filter would catch most
                    # phrases anyway, but skip the whole block to be safe.
                    in_phrase_block = True
                else:
                    in_phrase_block = False
                    cur_cat['words'].extend(extract_words(pos_m.group(2)))
            elif not in_phrase_block:
                cur_cat['words'].extend(extract_words(stripped))

    # ── Validate ──────────────────────────────────────────────────────
    if len(classes) < 6:
        print(f"WARNING: Only found {len(classes)} classes (expected 6). "
              f"Parser may need pattern adjustment.")

    total_words = sum(
        len(cat['words'])
        for cls in classes
        for sec in cls['sections']
        for cat in sec['categories']
    )

    return {
        'meta': {
            'source':           'Project Gutenberg E-Text #10681',
            'total_classes':    len(classes),
            'total_sections':   sum(len(c['sections']) for c in classes),
            'total_categories': cat_counter,
            'total_raw_words':  total_words,
            'parse_timestamp':  datetime.now(timezone.utc).isoformat(),
        },
        'classes': classes,
    }


def main():
    if not ROGET_FILE.exists():
        print(f"ERROR: {ROGET_FILE} not found. Run download_roget.py first.")
        sys.exit(1)

    print(f"Reading {ROGET_FILE} ...")
    text = ROGET_FILE.read_text(encoding='utf-8', errors='replace')

    print("Parsing ...")
    result = parse_roget(text)

    meta = result['meta']
    print(f"\nParse results:")
    print(f"  Classes:    {meta['total_classes']}")
    print(f"  Sections:   {meta['total_sections']}")
    print(f"  Categories: {meta['total_categories']}")
    print(f"  Raw words:  {meta['total_raw_words']:,}")

    # Validate expected structure
    if meta['total_classes'] != 6:
        print(f"  WARNING: Expected 6 classes, got {meta['total_classes']}")
    if meta['total_categories'] < 800:
        print(f"  WARNING: Expected ~1,035 categories, got {meta['total_categories']}")
    if meta['total_raw_words'] < 10_000:
        print(f"  WARNING: Expected >10,000 raw words, got {meta['total_raw_words']}")

    # Per-class summary
    print()
    for cls in result['classes']:
        cat_count  = sum(len(s['categories']) for s in cls['sections'])
        word_count = sum(len(c['words']) for s in cls['sections'] for c in s['categories'])
        print(f"  Class {cls['id']}: {cls['name']}")
        print(f"    Sections: {len(cls['sections'])}, "
              f"Categories: {cat_count}, Words: {word_count:,}")

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nWrote: {OUTPUT_FILE}")

    # Sample — show first category with a reasonable word count
    for cls in result['classes']:
        for sec in cls['sections']:
            for cat in sec['categories']:
                if len(cat['words']) >= 5:
                    print(f"\nSample category: [{cat['id']}] {cat['name']}")
                    print(f"  Words (first 10): {cat['words'][:10]}")
                    return


if __name__ == '__main__':
    main()
