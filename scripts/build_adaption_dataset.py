"""
build_adaption_dataset.py
Pre-build the prompt and completion columns for Adaption upload.

All template variables are substituted locally before upload so that
Adaption receives complete, ready-to-use text with no placeholders.

Usage:
    py -3.12 scripts/build_adaption_dataset.py
    py -3.12 scripts/build_adaption_dataset.py --input kaggle_export/discoveries_sample_50.parquet
    py -3.12 scripts/build_adaption_dataset.py --input kaggle_export/discoveries.parquet --output kaggle_export/adaption_full.parquet

Output columns Adaption expects:
    prompt      — complete instruction, no unfilled variables
    completion  — existing generated_description (or empty string if null)

All other columns are preserved and passed through as context.
"""

import argparse
import html
import re
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("pandas not installed. Run: py -3.12 -m pip install pandas pyarrow")
    sys.exit(1)

# ── Roget class names ────────────────────────────────────────────────────────

ROGET_CLASSES = {
    "Abstract Relations": "Abstract Relations",
    "Space":              "Space",
    "Matter":             "Matter",
    "Intellect":          "Intellect",
    "Volition":           "Volition",
    "Affections":         "Affections",
}

DEPTH_LABELS = {
    "deep":    "deep (≥ 0.70)",
    "shallow": "shallow (0.50–0.70)",
}


# ── Prompt builder ───────────────────────────────────────────────────────────

def build_prompt(row) -> str:
    """
    Build a complete, self-contained prompt for one discovery row.
    No template variables — all values substituted from the row.
    """
    ta   = str(row.get("term_a", "")).strip()
    tb   = str(row.get("term_b", "")).strip()
    depth  = row.get("desert_value", 0.0)
    near1  = str(row.get("nearest_term_1", "")).strip()
    near2  = str(row.get("nearest_term_2", "")).strip()
    near3  = str(row.get("nearest_term_3", "")).strip()
    dist1  = row.get("nearest_dist_1", 0.0)
    dist2  = row.get("nearest_dist_2", 0.0)
    dist3  = row.get("nearest_dist_3", 0.0)
    level  = str(row.get("level", "")).replace("_", "-")
    class_a = str(row.get("roget_class_a", "")).strip()
    class_b = str(row.get("roget_class_b", "")).strip()
    depth_class = DEPTH_LABELS.get(str(row.get("depth_class", "")), "deep")

    # Build Roget class line — omit if both are empty
    if class_a and class_b and class_a != class_b:
        roget_line = (
            f"Roget's Thesaurus classifies \"{ta}\" under {class_a} "
            f"and \"{tb}\" under {class_b}."
        )
    elif class_a:
        roget_line = f"Roget's Thesaurus classifies both terms under {class_a}."
    elif class_b:
        roget_line = f"Roget's Thesaurus classifies both terms under {class_b}."
    else:
        roget_line = (
            "Both terms are drawn from Roget's Thesaurus 1911 "
            f"(probe level: {level})."
        )

    # Build nearest-concepts block
    near_lines = []
    for term, dist in [(near1, dist1), (near2, dist2), (near3, dist3)]:
        if term:
            near_lines.append(f'  - "{term}" (distance: {dist:.4f})')
    near_block = "\n".join(near_lines) if near_lines else "  (none recorded)"

    prompt = f"""## Conceptual Gap Analysis — Semantic Desert

Two English words were probed in a 384-dimensional sentence embedding space: "{ta}" and "{tb}".

The probe found a {depth_class} semantic desert — a region where the embedding model encodes meaning but no word in a 36,125-term vocabulary is nearby.

**Desert depth:** {depth:.4f} (L2 distance on the unit sphere in 384d space)

**Nearest named concepts at the deepest interior point:**
{near_block}

**Context:** {roget_line}

---

**Task:** Name and describe the unnamed concept that resides in this semantic gap.

Requirements:
- State the concept name on the first line
- Describe it in 2–4 sentences
- Be direct — state what the concept IS, not what the probe found
- Use plain prose: no markdown, no asterisks, no bullet points
- Do not hedge with "might be" or "could represent" — commit to the concept
- The tone is that of a field researcher naming something encountered for the first time"""

    return prompt.strip()


# ── Completion cleaner ───────────────────────────────────────────────────────

def clean_completion(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Fix mojibake: UTF-8 read as Latin-1
    try:
        text = text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    # HTML entities
    text = html.unescape(text)
    # Markdown bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\\([*_])', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pre-build Adaption prompt/completion columns.")
    parser.add_argument(
        "--input", "-i",
        default="kaggle_export/discoveries_sample_50.parquet",
        help="Input parquet file (default: kaggle_export/discoveries_sample_50.parquet)"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output parquet file (default: same directory as input, suffixed _adaption)"
    )
    parser.add_argument(
        "--check-placeholders",
        action="store_true",
        help="Scan output for unfilled template placeholders and warn"
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / (input_path.stem + "_adaption.parquet")

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print()

    # Load
    df = pd.read_parquet(input_path)
    print(f"Loaded {len(df):,} rows, {len(df.columns)} columns")
    print(f"Columns: {list(df.columns)}")
    print()

    # Build prompt column
    print("Building prompt column ...")
    df["prompt"] = df.apply(build_prompt, axis=1)

    # Build completion column
    print("Cleaning completion column ...")
    if "generated_description" in df.columns:
        df["completion"] = df["generated_description"].apply(clean_completion)
        n_with_completion = (df["completion"] != "").sum()
        print(f"  Entries with existing completion: {n_with_completion} / {len(df)}")
    else:
        df["completion"] = ""
        print("  No generated_description column found — completion left empty")

    print()

    # Placeholder check
    if args.check_placeholders:
        print("Checking for unfilled placeholders ...")
        placeholder_pattern = re.compile(r'\{[a-z_]+(?::[^}]+)?\}')
        leaks = []
        for i, row in df.iterrows():
            found = placeholder_pattern.findall(row["prompt"])
            if found:
                leaks.append((i, row.get("term_a", "?"), row.get("term_b", "?"), found))
        if leaks:
            print(f"  WARNING: {len(leaks)} rows have placeholder leaks:")
            for idx, ta, tb, found in leaks[:10]:
                print(f"    Row {idx}: {ta} vs {tb} — {found}")
        else:
            print("  No placeholder leaks found. OK")
        print()

    # Show sample prompts
    print("Sample prompts (first 3 rows):")
    print("─" * 60)
    for _, row in df.head(3).iterrows():
        print(f"[{row['term_a']} vs {row['term_b']}]")
        print(row["prompt"][:400] + "...")
        if row["completion"]:
            print(f"COMPLETION: {row['completion'][:150]}...")
        else:
            print("COMPLETION: (empty — Adaption will generate)")
        print()

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    size_kb = output_path.stat().st_size / 1024
    print(f"Saved: {output_path}  ({size_kb:.1f} KB, {len(df):,} rows)")
    print()
    print("Upload this file to Adaption.")
    print("Column mapping:")
    print("  Prompt column:     prompt")
    print("  Completion column: completion  (or check 'I don't have completion'")
    print("                                  if you want Adaption to generate fresh)")


if __name__ == "__main__":
    main()