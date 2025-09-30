from sqlalchemy.sql import select
from typing import Iterable
from sqlalchemy import inspect as sa_inspect


def find_unknown_model_kwargs(model, kwargs: dict) -> list[str]:
    """
    Return list of unknown kwarg keys that are not part of the model's mapped attributes.
    - model: the SQLAlchemy model class (not instance)
    - kwargs: dict of incoming kwargs to validate
    """
    mapper = sa_inspect(model)
    # mapper.attrs includes columns and relationships; attr.key is the name callers use
    allowed = {attr.key for attr in mapper.attrs}
    # Optionally allow primary-key-only insertion / defaults, etc. For now, strict.
    return [k for k in kwargs.keys() if k not in allowed]


def get_required_columns(model) -> list[str]:
    """
    Columns that are NOT NULL and have no server/default and are not simple auto PKs.
    """
    cols = []
    for col in model.__table__.columns:
        # Exclude columns that have server defaults or client defaults or are autoincrement PKs
        has_default = col.default is not None or col.server_default is not None
        is_auto_pk = col.autoincrement is True and col.primary_key
        if not col.nullable and not has_default and not is_auto_pk:
            cols.append(col.name)
    return cols


def get_unique_column_sets(model) -> list[Iterable[str]]:
    """
    Return a list of unique column sets. Each item is an iterable of column names.
    Covers:
      - Column(unique=True)
      - UniqueConstraint in the table
      - Index(..., unique=True)
    """
    unique_sets = []

    # single-column unique attributes
    for col in model.__table__.columns:
        if col.unique:
            unique_sets.append([col.name])

    # UniqueConstraint objects (multi-column)
    for constraint in model.__table__.constraints:
        # UniqueConstraint type
        from sqlalchemy import UniqueConstraint
        if isinstance(constraint, UniqueConstraint):
            unique_sets.append([c.name for c in constraint.columns])

    # unique indexes
    for idx in model.__table__.indexes:
        if idx.unique:
            unique_sets.append([c.name for c in idx.columns])

    return unique_sets


async def find_unique_conflicts(db, model, kwargs: dict) -> set[str]:
    """
    Run pre-insert queries to detect existing rows that would violate unique constraints.
    Returns a set of column names that conflict (best-effort).
    """
    conflicts = set()
    unique_sets = get_unique_column_sets(model)

    for cols in unique_sets:
        # only check if all columns in this unique set are provided in kwargs
        if not all(c in kwargs for c in cols):
            continue

        # build condition
        from sqlalchemy import and_
        conditions = [getattr(model, c) == kwargs[c] for c in cols]
        q = select(model).where(and_(*conditions)).limit(1)

        res = await db.execute(q)
        existing = res.scalars().first()
        if existing is not None:
            # If a unique index spans multiple columns, include all of them
            conflicts.update(cols)

    return conflicts
