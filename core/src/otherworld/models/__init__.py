"""Pydantic domain models + SQLAlchemy ORM tables.

This package is the M0 deliverable (About/architecture.md §15): every data
shape in the system must exist here, as typed code, before any behaviour is
written on top of it.

Each module pairs a framework-agnostic Pydantic model (the shape used by
runtime code) with a SQLAlchemy ORM class (the persisted row), plus
`*_to_orm` / `*_from_orm` conversion functions. Pydantic models never import
SQLAlchemy types directly, so the domain layer stays storage-agnostic.
"""
