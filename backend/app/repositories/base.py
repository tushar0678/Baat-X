"""Tenant-safe repository base.

Every query built here is forced through ``business_id``. There is deliberately
no "get by id without tenant" helper - cross-tenant reads must be impossible by
construction, not by convention.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession, business_id: uuid.UUID) -> None:
        self.session = session
        self.business_id = business_id

    # ---------------- query helpers ----------------
    def base_query(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.business_id == self.business_id)  # type: ignore[attr-defined]

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        stmt = self.base_query().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        return (await self.session.execute(stmt)).scalars().first()

    async def get_or_404(self, entity_id: uuid.UUID) -> ModelT:
        entity = await self.get(entity_id)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} {entity_id} not found in tenant")
        return entity

    async def count(self, stmt: Select[Any] | None = None) -> int:
        stmt = stmt if stmt is not None else self.base_query()
        total = await self.session.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        return int(total.scalar_one())

    async def paginate(
        self, stmt: Select[tuple[ModelT]], params: PageParams
    ) -> tuple[list[ModelT], int]:
        total = await self.count(stmt)
        stmt = stmt.limit(params.page_size).offset(params.offset)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return list(rows), total

    # ---------------- writes ----------------
    def add(self, entity: ModelT) -> ModelT:
        entity.business_id = self.business_id  # type: ignore[attr-defined]
        self.session.add(entity)
        return entity

    async def flush(self) -> None:
        await self.session.flush()

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)

    def apply_sort(self, stmt: Select[Any], params: PageParams, allowed: dict[str, Any]):  # noqa: ANN201
        column = allowed.get(params.sort_by or "", None)
        if column is None:
            column = next(iter(allowed.values()))
        return stmt.order_by(column.asc() if params.sort_dir == "asc" else column.desc())
