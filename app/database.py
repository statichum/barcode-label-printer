from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import psycopg

from .config import Settings


ITEMS_SQL = """
SELECT DISTINCT ON (inventory_id)
    inventory_id,
    description,
    barcode
FROM sf_prodoptions
WHERE inventory_id = ANY(%s)
ORDER BY
    inventory_id,
    (barcode IS NOT NULL AND barcode <> '') DESC,
    description NULLS LAST
"""


@dataclass(frozen=True)
class CatalogItem:
    item_code: str
    description: str
    barcode: str | None

    @property
    def printable(self) -> bool:
        return bool(self.barcode)


class CatalogRepository:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _connect(self):
        return psycopg.connect(
            host=self.settings.database_host,
            port=self.settings.database_port,
            dbname=self.settings.database_name,
            user=self.settings.database_user,
            password=self.settings.database_password,
            connect_timeout=5,
        )

    def get_items(self, item_codes: Iterable[str]) -> dict[str, CatalogItem]:
        codes = list(dict.fromkeys(item_codes))
        if not codes:
            return {}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(ITEMS_SQL, (codes,))
                rows = cursor.fetchall()
        return {
            str(code): CatalogItem(
                item_code=str(code),
                description=str(description or code),
                barcode=str(barcode).strip() if barcode else None,
            )
            for code, description, barcode in rows
        }

    def check(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

