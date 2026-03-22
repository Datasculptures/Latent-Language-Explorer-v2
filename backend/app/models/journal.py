"""
backend/app/models/journal.py
Pydantic models for field journal entries.
All string inputs are validated and sanitized on ingestion.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field, field_validator

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
from terrain_config import (
    MAX_CONCEPT_LABEL_LENGTH, MAX_USER_NOTE_LENGTH,
    MAX_TAG_LENGTH, MAX_TAGS_PER_ENTRY, SCHEMA_VERSION,
)


def _sanitize_string(value: str) -> str:
    """Strip control characters and HTML-entity-encode angle brackets."""
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
    value = value.replace('<', '&lt;').replace('>', '&gt;')
    return value.strip()


class NearestConcept(BaseModel):
    term: str = Field(max_length=MAX_CONCEPT_LABEL_LENGTH)
    distance: float = Field(ge=0.0)
    roget_categories: list[str] | None = None
    roget_class: str | None = None

    @field_validator('term')
    @classmethod
    def sanitize_term(cls, v: str) -> str:
        return _sanitize_string(v)


class RogetContext(BaseModel):
    category_a: str
    category_b: str
    section_a: str | None = None
    section_b: str | None = None
    class_a: str | None = None
    class_b: str | None = None

    @field_validator('category_a','category_b','section_a','section_b','class_a','class_b', mode='before')
    @classmethod
    def sanitize_fields(cls, v):
        if v is None:
            return v
        return _sanitize_string(str(v))


class FabricationNotes(BaseModel):
    material:   str = Field(default="", max_length=200)
    method:     str = Field(default="", max_length=200)
    dimensions: str = Field(default="", max_length=200)
    status:     str = Field(default="idea")
    photos:     list[str] = Field(default_factory=list, max_length=20)

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"idea", "planned", "in_progress", "complete"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v

    @field_validator('photos')
    @classmethod
    def validate_photos(cls, v: list) -> list:
        return [_sanitize_string(p)[:500] for p in v[:20]]


class JournalEntryCreate(BaseModel):
    type:                   str = Field(default="manual")
    coordinates_2d:         list[float] = Field(min_length=2, max_length=2)
    coordinates_highD:      list[float] | None = None
    desert_value:           float = Field(default=0.0, ge=0.0)
    nearest_concepts:       list[NearestConcept] = Field(default_factory=list, max_length=10)
    roget_context:          RogetContext | None = None
    generated_description:  str | None = Field(default=None, max_length=1000)
    user_notes:             str = Field(default="", max_length=MAX_USER_NOTE_LENGTH)
    fabrication_notes:      FabricationNotes = Field(default_factory=FabricationNotes)
    tags:                   list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_ENTRY)
    starred:                bool = False
    v1_source:              dict[str, Any] | None = None

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"probe_discovery","dig_site","voronoi","manual","fabrication_note","v1_import"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v

    @field_validator('tags')
    @classmethod
    def sanitize_tags(cls, v: list) -> list:
        return [_sanitize_string(t)[:MAX_TAG_LENGTH] for t in v[:MAX_TAGS_PER_ENTRY]]

    @field_validator('user_notes', 'generated_description', mode='before')
    @classmethod
    def sanitize_text(cls, v):
        if v is None:
            return v
        return _sanitize_string(str(v))


class JournalEntry(JournalEntryCreate):
    id:             str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:      datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = SCHEMA_VERSION

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class JournalEntryUpdate(BaseModel):
    """All fields optional — only provided fields are updated."""
    user_notes:            str | None = Field(default=None, max_length=MAX_USER_NOTE_LENGTH)
    fabrication_notes:     FabricationNotes | None = None
    tags:                  list[str] | None = Field(default=None, max_length=MAX_TAGS_PER_ENTRY)
    starred:               bool | None = None
    generated_description: str | None = Field(default=None, max_length=1000)

    @field_validator('user_notes', 'generated_description', mode='before')
    @classmethod
    def sanitize_text(cls, v):
        if v is None:
            return v
        return _sanitize_string(str(v))

    @field_validator('tags', mode='before')
    @classmethod
    def sanitize_tags(cls, v):
        if v is None:
            return v
        from terrain_config import MAX_TAG_LENGTH, MAX_TAGS_PER_ENTRY
        return [_sanitize_string(t)[:MAX_TAG_LENGTH] for t in v[:MAX_TAGS_PER_ENTRY]]
