from __future__ import annotations

import json
import sqlite3
import time
from typing import Iterable

import pandas as pd

from startupper import util as util_mod
from startupper.persistence.domain_store import DomainStore


def _default_db_path() -> str:
    # Keep DB next to startupper package (same as previous behavior)
    return util_mod.get_db_full_path(util_mod.__file__)


class SQLiteDomainStore(DomainStore):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _default_db_path()

    def setup(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS domains (
                    name TEXT PRIMARY KEY,
                    available INTEGER,
                    definitive INTEGER,
                    price_error TEXT,
                    price REAL,
                    raw_json TEXT,
                    conceived INTEGER
                )
                """
            )
            try:
                c.execute("ALTER TABLE domains ADD COLUMN conceived INTEGER")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def get_existing_domains(self) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM domains")
            return {row[0] for row in c.fetchall()}

    def upsert_domain(self, name: str, info: dict) -> None:
        conceived = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR REPLACE INTO domains 
                (name, available, definitive, price_error, price, raw_json, conceived)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT conceived FROM domains WHERE name = ?), ?))
                """,
                (
                    name,
                    int(info.get("available", False)),
                    int(info.get("definitive", False)),
                    info.get("price_error", ""),
                    info.get("price", None),
                    json.dumps(info, ensure_ascii=False),
                    name,
                    conceived,
                ),
            )
            conn.commit()

    def select_domains(
        self,
        columns: Iterable[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
        desc: bool = False,
    ) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            if columns is None:
                c.execute("PRAGMA table_info(domains)")
                columns = [row[1] for row in c.fetchall()]
            col_str = ", ".join(columns)
            sql = f"SELECT {col_str} FROM domains"
            if order_by:
                sql += f" ORDER BY {order_by} {'DESC' if desc else ''}"
            if limit:
                sql += f" LIMIT {limit}"
            df = pd.read_sql_query(sql, conn)
            if "conceived" in df.columns:
                df["conceived"] = pd.to_datetime(df["conceived"], unit="s", errors="coerce")
            return df
