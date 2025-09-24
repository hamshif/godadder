from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

import pandas as pd


class DomainStore(ABC):
    """Abstract interface for persisting and querying domain check results.

    Implementations may use SQLite, Postgres, in-memory, etc.
    """

    @abstractmethod
    def setup(self) -> None:
        """Create storage structures if they don't exist."""

    @abstractmethod
    def get_existing_domains(self) -> set[str]:
        """Return set of domain names already stored."""

    @abstractmethod
    def upsert_domain(self, name: str, info: dict) -> None:
        """Insert or update a domain record with the provided info."""

    @abstractmethod
    def select_domains(
        self,
        columns: Iterable[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
        desc: bool = False,
    ) -> pd.DataFrame:
        """Return a DataFrame of stored domain rows."""

