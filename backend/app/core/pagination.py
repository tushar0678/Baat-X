from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(1, ge=1, le=10_000)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: str | None = None
    sort_dir: str = Field("desc", pattern="^(asc|desc)$")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_next: bool

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> "Page[T]":
        return cls(
            items=items,
            page=params.page,
            page_size=params.page_size,
            total=total,
            has_next=params.offset + len(items) < total,
        )
