"""
backend/app/routers/journal.py
Journal CRUD endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..models.journal import JournalEntryCreate, JournalEntryUpdate
from ..services.journal_store import get_store

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("")
async def list_entries(
    tags:                list[str] | None = Query(default=None),
    min_desert:          float | None     = Query(default=None, ge=0.0),
    starred:             bool | None      = Query(default=None),
    entry_type:          str | None       = Query(default=None),
    fabrication_status:  str | None       = Query(default=None),
    roget_class:         str | None       = Query(default=None),
    limit:               int              = Query(default=100, ge=1, le=1000),
    offset:              int              = Query(default=0, ge=0),
):
    store = get_store()
    all_entries = store.get_all()

    if any([tags, min_desert is not None, starred is not None,
            entry_type, fabrication_status, roget_class]):
        ids = store.query(
            tags=tags, min_desert=min_desert, starred=starred,
            entry_type=entry_type, fabrication_status=fabrication_status,
            roget_class=roget_class, limit=limit, offset=offset,
        )
        id_set = set(ids)
        entries = [e for e in all_entries if e.get('id') in id_set]
    else:
        entries = list(reversed(all_entries))[offset:offset + limit]

    return {"entries": entries, "total": len(all_entries)}


@router.get("/export")
async def export_journal():
    store = get_store()
    entries = store.get_all()
    return JSONResponse(
        content={"entries": entries, "count": len(entries)},
        headers={"Content-Disposition": 'attachment; filename="field_journal.json"'},
    )


@router.get("/{entry_id}")
async def get_entry(entry_id: str):
    entry_id = entry_id[:36]  # UUID length cap — never trust user-supplied IDs
    entry = get_store().get_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry


@router.post("", status_code=201)
async def create_entry(body: JournalEntryCreate):
    return get_store().create(body)


@router.put("/{entry_id}")
async def update_entry(entry_id: str, body: JournalEntryUpdate):
    entry_id = entry_id[:36]
    entry = get_store().update(entry_id, body)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry
