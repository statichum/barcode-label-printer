from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    myob_base_url: str
    myob_api_root: str
    myob_username: str
    myob_password: str
    myob_company: str
    myob_verify_ssl: bool
    myob_timeout_seconds: int
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: str
    printer_name: str
    printer_model: str
    printer_language: str
    printer_mac: str
    printer_port: int
    printer_ip_override: str | None
    arp_interface: str
    printer_connect_timeout_seconds: int
    printer_reopen_delay_ms: int
    print_enabled: bool
    label_width_mm: int
    label_height_mm: int
    printer_dots_per_mm: int
    data_dir: Path
    spool_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_int("APP_PORT", 4050),
            myob_base_url=os.getenv("MYOB_BASE_URL", "https://prv.myobadvanced.com").rstrip("/"),
            myob_api_root=os.getenv("MYOB_API_ROOT", "/entity/CustomExt/22.200.001"),
            myob_username=os.getenv("MYOB_USERNAME", ""),
            myob_password=os.getenv("MYOB_PASSWORD", ""),
            myob_company=os.getenv("MYOB_COMPANY", "PRV"),
            myob_verify_ssl=_bool("MYOB_VERIFY_SSL", True),
            myob_timeout_seconds=_int("MYOB_TIMEOUT_SECONDS", 45),
            database_host=os.getenv("DATABASE_HOST", "127.0.0.1"),
            database_port=_int("DATABASE_PORT", 5432),
            database_name=os.getenv("DATABASE_NAME", "prv-syncer"),
            database_user=os.getenv("DATABASE_USER", "prv-syncer"),
            database_password=os.getenv("DATABASE_PASSWORD", ""),
            printer_name=os.getenv("PRINTER_NAME", "sato-barcode"),
            printer_model=os.getenv("PRINTER_MODEL", "CG412DT-LAN"),
            printer_language=os.getenv("PRINTER_LANGUAGE", "SBPL"),
            printer_mac=os.getenv("PRINTER_MAC", "00:19:98:84:26:F9"),
            printer_port=_int("PRINTER_PORT", 9100),
            printer_ip_override=os.getenv("PRINTER_IP_OVERRIDE") or None,
            arp_interface=os.getenv("ARP_INTERFACE", "enp5s0"),
            printer_connect_timeout_seconds=_int("PRINTER_CONNECT_TIMEOUT_SECONDS", 3),
            printer_reopen_delay_ms=_int("PRINTER_REOPEN_DELAY_MS", 250),
            print_enabled=_bool("PRINT_ENABLED", False),
            label_width_mm=_int("LABEL_WIDTH_MM", 50),
            label_height_mm=_int("LABEL_HEIGHT_MM", 30),
            printer_dots_per_mm=_int("PRINTER_DOTS_PER_MM", 12),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
            spool_dir=Path(os.getenv("SPOOL_DIR", "/app/spool")),
        )

    @property
    def label_width_dots(self) -> int:
        return self.label_width_mm * self.printer_dots_per_mm

    @property
    def label_height_dots(self) -> int:
        return self.label_height_mm * self.printer_dots_per_mm

    def validate_runtime(self) -> list[str]:
        missing = []
        for name, value in (
            ("MYOB_USERNAME", self.myob_username),
            ("MYOB_PASSWORD", self.myob_password),
            ("DATABASE_PASSWORD", self.database_password),
            ("PRINTER_MAC", self.printer_mac),
        ):
            if not value:
                missing.append(name)
        return missing
