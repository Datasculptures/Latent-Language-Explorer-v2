"""
generate_instruction_sheet.py
Generate a fabrication instruction sheet for a field journal entry.

Reads a discovery entry from the journal by ID (or uses the deepest
entry if no ID is given) and produces a one-page PDF instruction sheet.

Usage:
  py scripts/generate_instruction_sheet.py \
     [--entry-id UUID] \
     [--title "My Discovery"] \
     [--output-dir backend/data/exports/]

If --entry-id is not given, uses the starred entry with the highest
desert_value from the journal.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
JOURNAL_FILE  = PROJECT_ROOT / "backend" / "data" / "journal" / "journal.json"
TERRAIN_FILE  = PROJECT_ROOT / "backend" / "data" / "terrain_data.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    EXPORT_DEFAULT_BASE_INCHES, EXPORT_DEFAULT_MAX_HEIGHT_INCHES,
    EXPORT_CONTOUR_INTERVAL_INCHES, EXPORT_DPI,
)


def safe_output_dir(path_str: str) -> Path:
    exports_root = (PROJECT_ROOT / "backend" / "data" / "exports").resolve()
    resolved     = Path(path_str).resolve()
    if not str(resolved).startswith(str(exports_root)):
        raise ValueError(f"Output path must be within {exports_root}.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def sanitize(s: str, max_len: int = 500) -> str:
    s = re.sub(r'[\x00-\x1f\x7f]', '', str(s))
    return s.strip()[:max_len]


# ── Material strategy heuristics ─────────────────────────────────────────────
# Derived from the four thematic families identified in V1 field notes.
# Deterministic — no LLM call.

def suggest_material_strategy(entry: dict) -> dict:
    """
    Suggest a material strategy based on discovery metadata.
    Returns dict with: strategy_name, material, method, rationale.
    """
    roget_ctx = entry.get('roget_context') or {}
    class_a   = str(roget_ctx.get('class_a', '') or '').lower()
    class_b   = str(roget_ctx.get('class_b', '') or '').lower()
    cat_a     = str(roget_ctx.get('category_a', '') or '').lower()
    cat_b     = str(roget_ctx.get('category_b', '') or '').lower()
    desc      = str(entry.get('generated_description', '') or '').lower()
    notes     = str(entry.get('user_notes', '') or '').lower()
    all_text  = ' '.join([class_a, class_b, cat_a, cat_b, desc, notes])
    desert    = entry.get('desert_value', 0.0)

    # Family: Time written into material
    if any(w in all_text for w in ['wear', 'rust', 'thin', 'age', 'duration',
                                    'material', 'making', 'matter', 'press']):
        return {
            'strategy_name': 'Duration inscribed in material',
            'material':      'Wire (annealed steel), worn wood, or handled cement',
            'method':        (
                'Bend wire repeatedly until it holds the shape. '
                'Sand wood along grain until surface memory shows. '
                'Press object into wet cement; let cure. '
                'The object should look used, not made.'
            ),
            'rationale': (
                'This discovery sits at the border of process and record. '
                'The material should carry evidence of effort, not just its result.'
            ),
        }

    # Family: Translation between registers
    if any(w in all_text for w in ['precision', 'control', 'stroke', 'digit',
                                    'execution', 'hand', 'machine', 'code', 'form']):
        return {
            'strategy_name': 'Translation between registers',
            'material':      'Ink on paper, or nails in wood at measured intervals',
            'method':        (
                'Rule a precise grid on cardboard. '
                'Mark the terrain contour intervals in ink — each line at exact height. '
                'Or: drive nails into a wood board at heights proportional to elevation. '
                'The precision is the point.'
            ),
            'rationale': (
                'This discovery describes the shared quality of disciplined execution '
                'across physical and digital media. The material process should enact it.'
            ),
        }

    # Family: Invisible infrastructure
    if any(w in all_text for w in ['scaffold', 'infrastructure', 'plumbing',
                                    'configuration', 'valve', 'rate', 'limit',
                                    'arrangement', 'system', 'volition']):
        return {
            'strategy_name': 'Invisible infrastructure',
            'material':      'Cardboard, paint, found objects from hardware store',
            'method':        (
                'Build a structure that only becomes visible from one angle. '
                'Use cardboard scored and folded at terrain contour intervals. '
                'Paint one face; leave the other raw. '
                'The work is what it hides as much as what it shows.'
            ),
            'rationale': (
                'This discovery concerns arrangements that enable without appearing. '
                'The sculpture should be readable as both object and infrastructure.'
            ),
        }

    # Family: Mechanism vs experience
    if any(w in all_text for w in ['sensation', 'feel', 'experience', 'chemical',
                                    'process', 'consciousness', 'transform',
                                    'become', 'emerge', 'affection']):
        return {
            'strategy_name': 'Border between mechanism and experience',
            'material':      'Two dissimilar materials joined at a visible seam',
            'method':        (
                'Join two unlike materials — smooth cement to rough wire, '
                'or painted wood to bare metal — at the desert location. '
                'The seam is the discovery. Do not hide it. '
                'The two materials should resist each other.'
            ),
            'rationale': (
                'This discovery sits at the gap between process and what the process '
                'feels like. The seam between materials enacts that gap physically.'
            ),
        }

    # Default: depth-based
    if desert >= 0.07:
        return {
            'strategy_name': 'Deep absence materialised',
            'material':      'Empty space held by minimal structure',
            'method':        (
                'Build a frame — four nails, wire perimeter, or bent rod — '
                'around an empty volume proportional to the desert depth. '
                f'Desert depth {desert:.3f} \u2192 interior void {desert*12:.1f}" across. '
                'The object is what surrounds nothing.'
            ),
            'rationale': (
                'Deep deserts are where the embedding model encodes meaning that '
                'language cannot name. The sculpture holds that absence as volume.'
            ),
        }

    return {
        'strategy_name': 'Terrain relief',
        'material':      'Layered cardboard or wood at 1/4" increments',
        'method':        (
            'Cut contour layers from the companion CSV using the contour diagram. '
            'Stack and glue in order. Sand edges. '
            f'Each 1/4" layer represents {EXPORT_CONTOUR_INTERVAL_INCHES}" of elevation.'
        ),
        'rationale': (
            'Direct materialisation of the terrain heightfield. '
            'The contour diagram is the cutting template.'
        ),
    }


def make_instruction_sheet(
    entry:      dict,
    terrain:    dict,
    title:      str,
    output_dir: Path,
) -> Path:
    """Generate a one-page instruction sheet PDF."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        print("ERROR: matplotlib required. Run: pip install matplotlib")
        sys.exit(1)

    import numpy as np

    strategy = suggest_material_strategy(entry)

    fig = plt.figure(figsize=(8.5, 11), dpi=EXPORT_DPI // 10)
    fig.patch.set_facecolor('white')

    gs = gridspec.GridSpec(3, 2, figure=fig,
                           hspace=0.4, wspace=0.3,
                           left=0.08, right=0.92,
                           top=0.92, bottom=0.05)

    # ── Header ──────────────────────────────────────────────────────────
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.axis('off')
    roget_ctx = entry.get('roget_context') or {}
    cat_a     = sanitize(roget_ctx.get('category_a', 'unknown'), 60)
    cat_b     = sanitize(roget_ctx.get('category_b', 'unknown'), 60)
    class_a   = sanitize(roget_ctx.get('class_a', ''), 40)
    class_b   = sanitize(roget_ctx.get('class_b', ''), 40)
    desert    = entry.get('desert_value', 0.0)
    depth_str = ('DEEP' if desert >= 0.05 else
                 'shallow' if desert >= 0.02 else 'flat')

    ax_header.text(0.0, 0.95, sanitize(title, 80),
                   transform=ax_header.transAxes,
                   fontsize=14, fontweight='bold', va='top')
    ax_header.text(0.0, 0.65,
                   f'{cat_a}  \u2194  {cat_b}',
                   transform=ax_header.transAxes,
                   fontsize=10, color='#333', va='top')
    ax_header.text(0.0, 0.35,
                   f'Class: {class_a} \u2194 {class_b}   '
                   f'Desert depth: {desert:.4f} [{depth_str}]   '
                   f'Type: {entry.get("type", "unknown")}',
                   transform=ax_header.transAxes,
                   fontsize=7, color='#666', va='top')
    ax_header.axhline(0, color='#ccc', linewidth=0.5)

    # ── Terrain patch (middle-left) ──────────────────────────────────────
    ax_terrain = fig.add_subplot(gs[1, 0])
    ux, uy = entry.get('coordinates_2d', [0, 0])
    if ux != 0 or uy != 0:
        from export_topo import sample_heightfield
        radius = 3.0  # UMAP units
        elev, xs, ys = sample_heightfield(
            density=           terrain['density'],
            x_grid=            terrain['x_grid'],
            y_grid=            terrain['y_grid'],
            grid_size=         32,
            focus_x=           ux, focus_y=uy, focus_radius=radius,
            max_height_inches= EXPORT_DEFAULT_MAX_HEIGHT_INCHES,
            contour_interval=  EXPORT_CONTOUR_INTERVAL_INCHES,
        )
        n_levels = int(EXPORT_DEFAULT_MAX_HEIGHT_INCHES / EXPORT_CONTOUR_INTERVAL_INCHES)
        levels = [i * EXPORT_CONTOUR_INTERVAL_INCHES for i in range(n_levels + 1)]
        ax_terrain.contourf(np.array(xs), np.array(ys), elev,
                            levels=levels, cmap='Blues', alpha=0.5)
        ax_terrain.contour(np.array(xs), np.array(ys), elev,
                           levels=levels, colors='black', linewidths=0.4)
        ax_terrain.scatter([ux], [uy], c='red', s=40, zorder=5)
    else:
        ax_terrain.text(0.5, 0.5, 'No position\n(CLI discovery)',
                        ha='center', va='center',
                        transform=ax_terrain.transAxes,
                        color='#999', fontsize=8)
    ax_terrain.set_title('Terrain patch', fontsize=7)
    ax_terrain.set_xlabel('UMAP x', fontsize=6)
    ax_terrain.set_ylabel('UMAP y', fontsize=6)
    ax_terrain.tick_params(labelsize=5)

    # ── Nearest concepts (middle-right) ──────────────────────────────────
    ax_concepts = fig.add_subplot(gs[1, 1])
    ax_concepts.axis('off')
    ax_concepts.set_title('Nearest concepts at deepest point', fontsize=7)
    nearest = entry.get('nearest_concepts', [])[:5]
    for i, c in enumerate(nearest):
        term = sanitize(c.get('term', ''), 30)
        dist = c.get('distance', 0.0)
        rc   = c.get('roget_class') or ''
        if not rc and c.get('roget_categories'):
            rc = c['roget_categories'][0]
        cat_label = sanitize(rc, 20)
        ax_concepts.text(0.0, 0.85 - i * 0.17,
                         f'{i+1}. {term}',
                         transform=ax_concepts.transAxes,
                         fontsize=8,
                         fontweight='bold' if i == 0 else 'normal')
        ax_concepts.text(0.0, 0.77 - i * 0.17,
                         f'   dist={dist:.4f}  class: {cat_label}',
                         transform=ax_concepts.transAxes,
                         fontsize=6, color='#666')

    # ── Description (bottom-left) ────────────────────────────────────────
    ax_desc = fig.add_subplot(gs[2, 0])
    ax_desc.axis('off')
    ax_desc.set_title('Generated description', fontsize=7)
    raw_desc = sanitize(
        entry.get('generated_description') or
        entry.get('user_notes') or
        '(no description)', 300)
    ax_desc.text(0.0, 0.95, raw_desc,
                 transform=ax_desc.transAxes,
                 fontsize=7, va='top', wrap=True,
                 fontstyle='italic', color='#333',
                 multialignment='left')

    # ── Material strategy (bottom-right) ─────────────────────────────────
    ax_mat = fig.add_subplot(gs[2, 1])
    ax_mat.axis('off')
    ax_mat.set_title(f'Material strategy: {strategy["strategy_name"]}', fontsize=7)
    mat_text = (
        f'Material: {strategy["material"]}\n\n'
        f'Method: {strategy["method"]}\n\n'
        f'Rationale: {strategy["rationale"]}'
    )
    ax_mat.text(0.0, 0.98, mat_text,
                transform=ax_mat.transAxes,
                fontsize=6, va='top', wrap=True,
                color='#333', multialignment='left')

    # ── Footer ────────────────────────────────────────────────────────────
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    fig.text(0.5, 0.01,
             f'Latent Language Explorer V2  \u00b7  datasculptures.com  \u00b7  {ts}',
             ha='center', fontsize=6, color='#aaa')

    ts_file  = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = output_dir / f"{title.replace(' ', '_')}_{ts_file}_sheet.pdf"
    fig.savefig(str(out_path), dpi=EXPORT_DPI, bbox_inches='tight')
    plt.close(fig)
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate fabrication instruction sheet for a journal entry.")
    parser.add_argument('--entry-id',   default=None)
    parser.add_argument('--title',      default=None)
    parser.add_argument('--output-dir', default='backend/data/exports/')
    args = parser.parse_args()

    try:
        output_dir = safe_output_dir(args.output_dir)
    except ValueError as e:
        print(f"ERROR: {e}"); sys.exit(1)

    for f in [JOURNAL_FILE, TERRAIN_FILE]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    with open(JOURNAL_FILE, encoding='utf-8') as f:
        entries = json.load(f)

    if not entries:
        print("ERROR: Journal is empty. Run discovery first.")
        sys.exit(1)

    # Find target entry
    entry = None
    if args.entry_id:
        eid   = sanitize(args.entry_id, 36)
        entry = next((e for e in entries if e.get('id') == eid), None)
        if entry is None:
            print(f"ERROR: Entry not found: {eid}")
            sys.exit(1)
    else:
        starred = [e for e in entries if e.get('starred')]
        pool    = starred if starred else entries
        entry   = max(pool, key=lambda e: e.get('desert_value', 0.0))
        print(f"Using entry: {entry.get('id')} "
              f"(desert={entry.get('desert_value', 0):.4f})")

    with open(TERRAIN_FILE, encoding='utf-8') as f:
        terrain = json.load(f)

    title = sanitize(
        args.title or entry.get('user_notes') or entry.get('id', 'discovery'),
        80,
    )

    print(f"Generating instruction sheet: '{title}' ...")
    out_path = make_instruction_sheet(entry, terrain, title, output_dir)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
