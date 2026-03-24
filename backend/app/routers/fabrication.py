"""
backend/app/routers/fabrication.py
Fabrication export endpoints.

POST /api/export/topo         — trigger topography export
POST /api/export/stl          — trigger STL export
POST /api/export/sheet        — trigger instruction sheet export
GET  /api/exports             — list available export files
GET  /api/exports/{filename}  — download an export file
"""
import re
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["fabrication"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EXPORTS_DIR  = PROJECT_ROOT / "backend" / "data" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

SCRIPTS_DIR = PROJECT_ROOT / "scripts"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    EXPORT_DEFAULT_GRID_SIZE, EXPORT_DEFAULT_BASE_INCHES,
    EXPORT_DEFAULT_MAX_HEIGHT_INCHES, EXPORT_CONTOUR_INTERVAL_INCHES,
    EXPORT_MAX_GRID_DIMENSION,
)


def _safe_filename(name: str) -> str:
    """Strip path separators and control characters from a filename."""
    name = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', '', name)
    return name.strip()[:100]


class TopoExportRequest(BaseModel):
    title:              str   = Field(default='terrain', max_length=80)
    grid_size:          int   = Field(default=EXPORT_DEFAULT_GRID_SIZE, ge=4, le=256)
    base_size:          float = Field(default=EXPORT_DEFAULT_BASE_INCHES, gt=0, le=120)
    max_height:         float = Field(default=EXPORT_DEFAULT_MAX_HEIGHT_INCHES, gt=0, le=120)
    contour_interval:   float = Field(default=EXPORT_CONTOUR_INTERVAL_INCHES, gt=0)
    overlay_attractors: bool  = False
    overlay_desert:     bool  = False
    overlay_journal:    bool  = False
    focus_x:            float | None = None
    focus_y:            float | None = None
    focus_radius:       float | None = None


class StlExportRequest(BaseModel):
    title:        str   = Field(default='terrain', max_length=80)
    grid_size:    int   = Field(default=EXPORT_DEFAULT_GRID_SIZE, ge=4, le=256)
    base_size:    float = Field(default=EXPORT_DEFAULT_BASE_INCHES, gt=0, le=120)
    max_height:   float = Field(default=EXPORT_DEFAULT_MAX_HEIGHT_INCHES, gt=0, le=120)
    focus_x:      float | None = None
    focus_y:      float | None = None
    focus_radius: float | None = None


class SheetExportRequest(BaseModel):
    entry_id: str | None = Field(default=None, max_length=36)
    title:    str | None = Field(default=None, max_length=80)


def _run_script(script_name: str, args: list[str]) -> dict:
    """
    Run a pipeline script as a subprocess.
    Returns {'ok': bool, 'files': list[str], 'error': str}.
    """
    import subprocess
    import os
    script = SCRIPTS_DIR / script_name
    if not script.exists():
        return {'ok': False, 'error': f'{script_name} not found'}

    # Ensure the venv site-packages are on PYTHONPATH for the subprocess.
    # The venv root is PROJECT_ROOT's parent (LLEv2/); packages live in Lib/site-packages.
    venv_site = PROJECT_ROOT.parent / "Lib" / "site-packages"
    env = os.environ.copy()
    if venv_site.exists():
        existing = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = str(venv_site) + (os.pathsep + existing if existing else '')

    cmd    = [sys.executable, str(script)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        timeout=120,
    )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or 'unknown error')[:500]
        return {'ok': False, 'error': detail}

    # Collect files written within the last 30 seconds
    now   = time.time()
    files = sorted(
        f.name for f in EXPORTS_DIR.iterdir()
        if f.is_file() and (now - f.stat().st_mtime) < 30
    )
    return {'ok': True, 'files': files, 'stdout': result.stdout[-500:]}


@router.post("/export/topo")
async def export_topo(req: TopoExportRequest):
    title = _safe_filename(req.title)
    args  = [
        '--title',            title,
        '--grid-size',        str(req.grid_size),
        '--base-size',        str(req.base_size),
        '--max-height',       str(req.max_height),
        '--contour-interval', str(req.contour_interval),
        '--output-dir',       str(EXPORTS_DIR),
    ]
    if req.overlay_attractors:
        args.append('--overlay-attractors')
    if req.overlay_desert:
        args.append('--overlay-desert')
    if req.overlay_journal:
        args.append('--overlay-journal')
    if req.focus_x is not None:
        args += ['--focus-x', str(req.focus_x),
                 '--focus-y', str(req.focus_y),
                 '--focus-radius', str(req.focus_radius)]

    result = _run_script('export_topo.py', args)
    if not result['ok']:
        raise HTTPException(status_code=500, detail=result['error'])
    return {'files': result['files'], 'title': title}


@router.post("/export/stl")
async def export_stl(req: StlExportRequest):
    title = _safe_filename(req.title)
    args  = [
        '--title',      title,
        '--grid-size',  str(req.grid_size),
        '--base-size',  str(req.base_size),
        '--max-height', str(req.max_height),
        '--output-dir', str(EXPORTS_DIR),
    ]
    if req.focus_x is not None:
        args += ['--focus-x', str(req.focus_x),
                 '--focus-y', str(req.focus_y),
                 '--focus-radius', str(req.focus_radius)]

    result = _run_script('export_stl.py', args)
    if not result['ok']:
        raise HTTPException(status_code=500, detail=result['error'])
    return {'files': result['files'], 'title': title}


@router.post("/export/sheet")
async def export_sheet(req: SheetExportRequest):
    args = ['--output-dir', str(EXPORTS_DIR)]
    if req.entry_id:
        args += ['--entry-id', _safe_filename(req.entry_id)[:36]]
    if req.title:
        args += ['--title', _safe_filename(req.title)]

    result = _run_script('generate_instruction_sheet.py', args)
    if not result['ok']:
        raise HTTPException(status_code=500, detail=result['error'])
    return {'files': result['files'], 'title': req.title}


@router.get("/exports")
async def list_exports():
    """List all files in the exports directory."""
    if not EXPORTS_DIR.exists():
        return {'files': []}
    files = sorted(
        [
            {
                'name':     f.name,
                'size':     f.stat().st_size,
                'modified': f.stat().st_mtime,
            }
            for f in EXPORTS_DIR.iterdir()
            if f.is_file() and not f.name.startswith('.')
        ],
        key=lambda x: x['modified'],
        reverse=True,
    )
    return {'files': files}


@router.get("/exports/{filename}")
async def download_export(filename: str):
    """Download a specific export file."""
    safe_name = _safe_filename(filename)
    file_path = (EXPORTS_DIR / safe_name).resolve()
    if not str(file_path).startswith(str(EXPORTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    suffix = file_path.suffix.lower()
    media_types = {
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.csv': 'text/csv',
        '.stl': 'application/octet-stream',
    }
    media_type = media_types.get(suffix, 'application/octet-stream')
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={'Content-Disposition': f'attachment; filename="{safe_name}"'},
    )
