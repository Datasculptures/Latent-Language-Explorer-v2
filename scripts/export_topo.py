"""
export_topo.py
Export terrain heightfield as a fabrication-ready topography diagram.

Outputs (in --output-dir):
  {title}_{timestamp}.pdf     — 300 DPI contour diagram
  {title}_{timestamp}.png     — same as PDF but PNG
  {title}_{timestamp}.csv     — elevation grid (rows × cols)

Usage:
  py scripts/export_topo.py \
     [--title "My Discovery"] \
     [--grid-size 48] \
     [--base-size 12.0] \
     [--max-height 6.0] \
     [--output-dir backend/data/exports/] \
     [--overlay-attractors] \
     [--overlay-desert] \
     [--overlay-journal] \
     [--focus-x FLOAT --focus-y FLOAT --focus-radius FLOAT]

If --focus-x/y/radius are given, the export crops to that region
of the terrain (useful for exporting a specific discovery location).
"""

import argparse
import csv
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRAIN_FILE = PROJECT_ROOT / "backend" / "data" / "terrain_data.json"
BUNDLE_FILE  = PROJECT_ROOT / "backend" / "data" / "data_bundle.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    EXPORT_DEFAULT_GRID_SIZE, EXPORT_DEFAULT_BASE_INCHES,
    EXPORT_DEFAULT_MAX_HEIGHT_INCHES, EXPORT_CONTOUR_INTERVAL_INCHES,
    EXPORT_DPI, EXPORT_MAX_GRID_DIMENSION,
)

# Roget class colours for attractor labels (matches frontend)
ROGET_CLASS_COLOURS = {
    1: '#00b4d8',
    2: '#e040a0',
    3: '#f07020',
    4: '#4ecb71',
    5: '#a070e0',
    6: '#e05050',
}


def safe_output_dir(path_str: str) -> Path:
    """Resolve output path and confirm it stays within backend/data/exports/."""
    exports_root = (PROJECT_ROOT / "backend" / "data" / "exports").resolve()
    resolved     = Path(path_str).resolve()
    if not str(resolved).startswith(str(exports_root)):
        raise ValueError(
            f"Output path must be within {exports_root}. "
            f"Rejected: {resolved}"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def sanitize_title(title: str) -> str:
    """Strip control characters and limit length for filename use."""
    title = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', '', title)
    return title.strip()[:80] or "terrain"


def sample_heightfield(
    density:           list,
    x_grid:            list,
    y_grid:            list,
    grid_size:         int,
    focus_x,
    focus_y,
    focus_radius,
    max_height_inches: float,
    contour_interval:  float,
):
    """
    Sample the terrain density grid onto a fabrication grid.
    Returns (elevation_grid, x_samples, y_samples).
    Elevation is in inches, quantized to contour_interval.
    """
    density_arr = np.array(density, dtype=np.float32)

    # Determine sampling bounds
    if focus_x is not None and focus_y is not None and focus_radius is not None:
        x_min = float(focus_x - focus_radius)
        x_max = float(focus_x + focus_radius)
        y_min = float(focus_y - focus_radius)
        y_max = float(focus_y + focus_radius)
    else:
        x_min, x_max = float(x_grid[0]),  float(x_grid[-1])
        y_min, y_max = float(y_grid[0]),  float(y_grid[-1])

    x_samples = np.linspace(x_min, x_max, grid_size).tolist()
    y_samples = np.linspace(y_min, y_max, grid_size).tolist()

    # Bilinear interpolation onto fabrication grid
    xg  = np.array(x_grid)
    yg  = np.array(y_grid)
    elev = np.zeros((grid_size, grid_size), dtype=np.float32)

    for ri, uy in enumerate(y_samples):
        for ci, ux in enumerate(x_samples):
            xi = max(0, min(int(np.searchsorted(xg, ux)) - 1, len(xg) - 2))
            yi = max(0, min(int(np.searchsorted(yg, uy)) - 1, len(yg) - 2))
            tx = np.clip((ux - xg[xi]) / (xg[xi+1] - xg[xi] + 1e-8), 0, 1)
            ty = np.clip((uy - yg[yi]) / (yg[yi+1] - yg[yi] + 1e-8), 0, 1)
            v  = (density_arr[yi,   xi]   * (1-tx) * (1-ty) +
                  density_arr[yi,   xi+1] *    tx  * (1-ty) +
                  density_arr[yi+1, xi]   * (1-tx) *    ty  +
                  density_arr[yi+1, xi+1] *    tx  *    ty)
            h = float(v) * max_height_inches
            h = round(h / contour_interval) * contour_interval
            elev[ri, ci] = h

    return elev, x_samples, y_samples


def write_csv(path, elev, x_samples, y_samples, contour_interval):
    """Write elevation grid as CSV with row/column headers."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['y\\x'] + [f'{x:.4f}' for x in x_samples])
        for ri, y in enumerate(y_samples):
            row = [f'{y:.4f}'] + [
                f'{elev[ri, ci]:.4f}' for ci in range(len(x_samples))
            ]
            writer.writerow(row)


def draw_diagram(
    elev, x_samples, y_samples, title, grid_size,
    base_inches, max_height_inches, contour_interval,
    terrain_data, bundle_data,
    overlay_attractors, overlay_desert, overlay_journal,
):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 1, figsize=(10, 10), dpi=EXPORT_DPI // 10)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    X      = np.array(x_samples)
    Y      = np.array(y_samples)
    levels = np.arange(0, max_height_inches + contour_interval, contour_interval)

    ax.contourf(X, Y, elev, levels=levels, cmap='Blues', alpha=0.4)
    cs = ax.contour(X, Y, elev, levels=levels,
                    colors='black', linewidths=0.5, alpha=0.7)
    dec = len(str(contour_interval).split('.')[-1]) if '.' in str(contour_interval) else 0
    ax.clabel(cs, fmt=f'%.{dec}f"', fontsize=6, inline=True)

    # Desert overlay — shade regions with desert > 0.65
    if overlay_desert and 'desert' in terrain_data:
        desert = np.array(terrain_data['desert'], dtype=np.float32)
        xg_arr = np.array(terrain_data['x_grid'])
        yg_arr = np.array(terrain_data['y_grid'])
        desert_resampled = np.zeros((grid_size, grid_size), dtype=np.float32)
        for ri, uy in enumerate(y_samples):
            for ci, ux in enumerate(x_samples):
                xi = int(np.argmin(np.abs(xg_arr - ux)))
                yi = int(np.argmin(np.abs(yg_arr - uy)))
                desert_resampled[ri, ci] = desert[yi, xi]
        ax.contourf(X, Y, desert_resampled, levels=[0.65, 1.0],
                    colors=['orange'], alpha=0.15)

    # Attractor overlay
    if overlay_attractors and 'attractors' in terrain_data:
        for attr in terrain_data['attractors']:
            ux, uy = attr['umap_x'], attr['umap_y']
            if (min(x_samples) <= ux <= max(x_samples) and
                    min(y_samples) <= uy <= max(y_samples)):
                marker = '*' if attr.get('is_major') else '+'
                size   = 120 if attr.get('is_major') else 60
                ax.scatter(ux, uy, marker=marker, s=size,
                           c='black', zorder=5, linewidths=0.8)

    # Journal overlay
    if overlay_journal:
        for entry in overlay_journal:
            ux, uy = entry.get('coordinates_2d', [0, 0])
            if ux == 0 and uy == 0:
                continue
            if (min(x_samples) <= ux <= max(x_samples) and
                    min(y_samples) <= uy <= max(y_samples)):
                col = '#ffd700' if entry.get('starred') else '#ff4400'
                ax.scatter(ux, uy, marker='o', s=40,
                           c=col, zorder=6, linewidths=0)

    ax.set_xticks(np.linspace(min(x_samples), max(x_samples), 7))
    ax.set_yticks(np.linspace(min(y_samples), max(y_samples), 7))
    ax.tick_params(labelsize=6)
    ax.grid(True, alpha=0.2, linewidth=0.3)

    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    fig.suptitle(
        f'{title}\n'
        f'Grid: {grid_size}\xd7{grid_size} \xb7 Base: {base_inches}" \xd7 {base_inches}" \xb7 '
        f'Max height: {max_height_inches}" \xb7 Interval: {contour_interval}" \xb7 {ts}',
        fontsize=7, y=0.02, va='bottom',
    )
    ax.set_aspect('equal')
    ax.set_xlabel('UMAP x', fontsize=7)
    ax.set_ylabel('UMAP y', fontsize=7)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    return fig


def main():
    parser = argparse.ArgumentParser(description="Export terrain topography diagram.")
    parser.add_argument('--title',            default='terrain')
    parser.add_argument('--grid-size',        type=int,   default=EXPORT_DEFAULT_GRID_SIZE)
    parser.add_argument('--base-size',        type=float, default=EXPORT_DEFAULT_BASE_INCHES)
    parser.add_argument('--max-height',       type=float, default=EXPORT_DEFAULT_MAX_HEIGHT_INCHES)
    parser.add_argument('--contour-interval', type=float, default=EXPORT_CONTOUR_INTERVAL_INCHES)
    parser.add_argument('--output-dir',       default='backend/data/exports/')
    parser.add_argument('--overlay-attractors', action='store_true')
    parser.add_argument('--overlay-desert',     action='store_true')
    parser.add_argument('--overlay-journal',    action='store_true')
    parser.add_argument('--focus-x',      type=float, default=None)
    parser.add_argument('--focus-y',      type=float, default=None)
    parser.add_argument('--focus-radius', type=float, default=None)
    args = parser.parse_args()

    # ── Input validation ───────────────────────────────────────────────────
    if args.grid_size < 4 or args.grid_size > EXPORT_MAX_GRID_DIMENSION:
        print(f"ERROR: grid_size must be 4\u2013{EXPORT_MAX_GRID_DIMENSION}.")
        sys.exit(1)
    if args.base_size <= 0 or args.base_size > 120:
        print("ERROR: base_size must be between 0 and 120 inches.")
        sys.exit(1)
    if args.max_height <= 0 or args.max_height > 120:
        print("ERROR: max_height must be between 0 and 120 inches.")
        sys.exit(1)
    if args.contour_interval <= 0:
        print("ERROR: contour_interval must be positive.")
        sys.exit(1)

    title = sanitize_title(args.title)

    try:
        output_dir = safe_output_dir(args.output_dir)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    for f in [TERRAIN_FILE, BUNDLE_FILE]:
        if not f.exists():
            print(f"ERROR: {f} not found. Run assemble_bundle.py first.")
            sys.exit(1)

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading terrain data ...")
    with open(TERRAIN_FILE, encoding='utf-8') as f:
        terrain = json.load(f)
    with open(BUNDLE_FILE, encoding='utf-8') as f:
        bundle = json.load(f)

    journal_entries = None
    if args.overlay_journal:
        journal_file = PROJECT_ROOT / "backend" / "data" / "journal" / "journal.json"
        if journal_file.exists():
            with open(journal_file, encoding='utf-8') as f:
                journal_entries = json.load(f)
            print(f"  Loaded {len(journal_entries)} journal entries for overlay.")
        else:
            print("  No journal file found — skipping journal overlay.")

    # ── Sample heightfield ─────────────────────────────────────────────────
    print(f"Sampling heightfield to {args.grid_size}\xd7{args.grid_size} grid ...")
    elev, x_samples, y_samples = sample_heightfield(
        density=           terrain['density'],
        x_grid=            terrain['x_grid'],
        y_grid=            terrain['y_grid'],
        grid_size=         args.grid_size,
        focus_x=           args.focus_x,
        focus_y=           args.focus_y,
        focus_radius=      args.focus_radius,
        max_height_inches= args.max_height,
        contour_interval=  args.contour_interval,
    )
    print(f"  Elevation range: {float(elev.min()):.3f}\" \u2013 {float(elev.max()):.3f}\"")

    # ── Write CSV ──────────────────────────────────────────────────────────
    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    stem     = f"{title.replace(' ', '_')}_{ts}"
    csv_path = output_dir / f"{stem}.csv"
    write_csv(csv_path, elev, x_samples, y_samples, args.contour_interval)
    print(f"Wrote CSV: {csv_path}")

    # ── Draw diagram ───────────────────────────────────────────────────────
    try:
        import matplotlib  # noqa: F401
        print("Drawing contour diagram ...")
        fig = draw_diagram(
            elev=               elev,
            x_samples=          x_samples,
            y_samples=          y_samples,
            title=              title,
            grid_size=          args.grid_size,
            base_inches=        args.base_size,
            max_height_inches=  args.max_height,
            contour_interval=   args.contour_interval,
            terrain_data=       terrain,
            bundle_data=        bundle,
            overlay_attractors= args.overlay_attractors,
            overlay_desert=     args.overlay_desert,
            overlay_journal=    journal_entries,
        )
        import matplotlib.pyplot as plt
        pdf_path = output_dir / f"{stem}.pdf"
        png_path = output_dir / f"{stem}.png"
        fig.savefig(str(pdf_path), dpi=EXPORT_DPI, bbox_inches='tight')
        fig.savefig(str(png_path), dpi=EXPORT_DPI, bbox_inches='tight')
        plt.close(fig)
        print(f"Wrote PDF: {pdf_path}")
        print(f"Wrote PNG: {png_path}")
    except ImportError:
        print("WARNING: matplotlib not installed \u2014 skipping diagram. CSV written.")

    print(f"\nExport complete: {output_dir}")


if __name__ == "__main__":
    main()
