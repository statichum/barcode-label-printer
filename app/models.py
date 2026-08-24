from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PurchaseOrderLookupRequest(BaseModel):
    po_number: str = Field(min_length=1, max_length=40)

    @field_validator("po_number")
    @classmethod
    def clean_po_number(cls, value: str) -> str:
        value = value.strip()
        if not value or not all(char.isalnum() or char in "-_" for char in value):
            raise ValueError("Enter a valid purchase order number")
        return value


class ManualItemLookupRequest(BaseModel):
    item_codes: list[str] = Field(min_length=1, max_length=100)

    @field_validator("item_codes")
    @classmethod
    def clean_codes(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            code = value.strip()
            if not code or len(code) > 80 or any(ord(char) < 32 for char in code):
                raise ValueError("One or more item codes are invalid")
            if code not in cleaned:
                cleaned.append(code)
        if not cleaned:
            raise ValueError("Enter at least one item code")
        return cleaned


class PrintItemRequest(BaseModel):
    item_code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=999)


class PrintRequest(BaseModel):
    items: list[PrintItemRequest] = Field(min_length=1, max_length=100)
    source: str = Field(default="manual", max_length=20)
    reference: str | None = Field(default=None, max_length=80)

    @field_validator("items")
    @classmethod
    def limit_total_labels(cls, values: list[PrintItemRequest]) -> list[PrintItemRequest]:
        if sum(item.quantity for item in values) > 2000:
            raise ValueError("A print job cannot exceed 2,000 labels")
        return values

