"""Plane 1 — Owner. See About/architecture.md §9.1."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, EmailStr
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base

OwnerStatus = Literal["active", "lapsed", "suspended", "deleted"]


class IdentityMode(StrEnum):
    REAL_NAME = "real_name"
    PSEUDONYMOUS = "pseudonymous"
    ANONYMOUS = "anonymous"


class VisibilityScope(StrEnum):
    PUBLIC = "public"
    FRIENDS = "friends"
    PRIVATE = "private"


class ConsentFlags(BaseModel):
    identity_mode: IdentityMode
    visibility_scope: VisibilityScope
    third_party_consent_intent: bool
    liability_acknowledged: bool
    tos_version: str
    acknowledged_at: datetime


class Owner(BaseModel):
    id: uuid.UUID
    handle: str
    email: EmailStr
    consent: ConsentFlags | None = None
    created_at: datetime
    last_active_at: datetime
    status: OwnerStatus = "active"


class OwnerORM(Base):
    __tablename__ = "owners"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    handle: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    consent: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="active")


def owner_to_orm(owner: Owner) -> OwnerORM:
    return OwnerORM(
        id=owner.id,
        handle=owner.handle,
        email=owner.email,
        consent=owner.consent.model_dump(mode="json") if owner.consent else None,
        created_at=owner.created_at,
        last_active_at=owner.last_active_at,
        status=owner.status,
    )


def owner_from_orm(row: OwnerORM) -> Owner:
    return Owner(
        id=row.id,
        handle=row.handle,
        email=row.email,
        consent=ConsentFlags.model_validate(row.consent) if row.consent else None,
        created_at=row.created_at,
        last_active_at=row.last_active_at,
        status=row.status,
    )
