from __future__ import annotations

import re

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
            code = value.strip().upper()
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

    @field_validator("item_code")
    @classmethod
    def clean_item_code(cls, value: str) -> str:
        return value.strip().upper()


class PrintRequest(BaseModel):
    items: list[PrintItemRequest] = Field(min_length=1, max_length=350)
    source: str = Field(default="manual", max_length=20)
    reference: str | None = Field(default=None, max_length=80)

    @field_validator("items")
    @classmethod
    def limit_total_labels(cls, values: list[PrintItemRequest]) -> list[PrintItemRequest]:
        if sum(item.quantity for item in values) > 2000:
            raise ValueError("A print job cannot exceed 2,000 labels")
        return values


class StaffLabelPrintRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    badge_code: str = Field(min_length=13, max_length=13)
    quantity: int = Field(default=1, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned or any(ord(char) < 32 for char in cleaned):
            raise ValueError("Enter a valid staff name")
        return cleaned

    @field_validator("badge_code")
    @classmethod
    def clean_badge_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"PPU-[A-Z0-9]{4}-[A-Z0-9]{4}", cleaned):
            raise ValueError("Staff badge code must use the PPU- format")
        return cleaned


class BarcodeAdminLoginRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=12, pattern=r"^[0-9]+$")


class BarcodeAssignmentPreviewRequest(BaseModel):
    # The normal 350-item limit is enforced against the authenticated admin
    # session. This upper bound is only a defensive request-size ceiling.
    item_codes: list[str] = Field(min_length=1, max_length=20_000)

    @field_validator("item_codes")
    @classmethod
    def clean_item_codes(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            code = value.strip().upper()
            if not code or len(code) > 80 or any(ord(char) < 32 for char in code):
                raise ValueError("One or more item codes are invalid")
            if code not in cleaned:
                cleaned.append(code)
        if not cleaned:
            raise ValueError("Select at least one item")
        return cleaned


class BarcodeAssignmentCommitRequest(BaseModel):
    preview_token: str = Field(min_length=20, max_length=200)
