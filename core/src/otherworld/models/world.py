"""Plane 5 — World. See About/architecture.md §9.6."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from otherworld.db import Base

WorldStatus = Literal["open", "full", "archived"]


class TerrainType(StrEnum):
    GRASS = "grass"
    PATH = "path"
    WATER = "water"
    WALL = "wall"
    FLOOR = "floor"
    FOREST = "forest"


class Tile(BaseModel):
    x: int
    y: int
    terrain: TerrainType
    walkable: bool
    zone_id: uuid.UUID | None = None


class Feature(BaseModel):
    id: uuid.UUID
    x: int
    y: int
    kind: str  # bench, well, workbench, resource node
    state: dict[str, Any] = {}


class Zone(BaseModel):
    id: uuid.UUID
    world_id: uuid.UUID
    name: str
    bounds: tuple[int, int, int, int]  # x0, y0, x1, y1


class World(BaseModel):
    id: uuid.UUID
    name: str
    width: int
    height: int
    current_tick: int = 0
    population: int = 0
    population_cap: int
    status: WorldStatus = "open"
    created_at: datetime


class WorldORM(Base):
    __tablename__ = "worlds"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    current_tick: Mapped[int] = mapped_column(Integer, default=0)
    population: Mapped[int] = mapped_column(Integer, default=0)
    population_cap: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ZoneORM(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String)
    bounds: Mapped[list[int]] = mapped_column(JSON)


class FeatureORM(Base):
    __tablename__ = "features"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TileORM(Base):
    __tablename__ = "tiles"
    __table_args__ = (UniqueConstraint("world_id", "x", "y", name="uq_tile_position"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    terrain: Mapped[str] = mapped_column(String)
    walkable: Mapped[bool] = mapped_column(Boolean)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


def world_to_orm(world: World) -> WorldORM:
    return WorldORM(
        id=world.id,
        name=world.name,
        width=world.width,
        height=world.height,
        current_tick=world.current_tick,
        population=world.population,
        population_cap=world.population_cap,
        status=world.status,
        created_at=world.created_at,
    )


def world_from_orm(row: WorldORM) -> World:
    return World(
        id=row.id,
        name=row.name,
        width=row.width,
        height=row.height,
        current_tick=row.current_tick,
        population=row.population,
        population_cap=row.population_cap,
        status=row.status,
        created_at=row.created_at,
    )


def zone_to_orm(zone: Zone) -> ZoneORM:
    return ZoneORM(id=zone.id, world_id=zone.world_id, name=zone.name, bounds=list(zone.bounds))


def zone_from_orm(row: ZoneORM) -> Zone:
    return Zone(id=row.id, world_id=row.world_id, name=row.name, bounds=tuple(row.bounds))


def feature_to_orm(feature: Feature, world_id: uuid.UUID) -> FeatureORM:
    return FeatureORM(
        id=feature.id, world_id=world_id, x=feature.x, y=feature.y, kind=feature.kind, state=feature.state
    )


def feature_from_orm(row: FeatureORM) -> Feature:
    return Feature(id=row.id, x=row.x, y=row.y, kind=row.kind, state=row.state)


def tile_to_orm(tile: Tile, world_id: uuid.UUID) -> TileORM:
    return TileORM(
        world_id=world_id,
        x=tile.x,
        y=tile.y,
        terrain=tile.terrain.value,
        walkable=tile.walkable,
        zone_id=tile.zone_id,
    )


def tile_from_orm(row: TileORM) -> Tile:
    return Tile(
        x=row.x, y=row.y, terrain=TerrainType(row.terrain), walkable=row.walkable, zone_id=row.zone_id
    )
