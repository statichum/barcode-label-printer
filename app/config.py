from __future__ import annotations

import os
from dataclasses import dataclass, replace
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
    barcode_admin_pin: str
    barcode_admin_session_minutes: int
    barcode_assignment_enabled: bool
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
    printer_send_timeout_seconds: int
    printer_reopen_delay_ms: int
    printer_send_attempts: int
    printer_retry_delay_ms: int
    printer_print_speed: int
    printer_darkness: str
    print_enabled: bool
    label_width_mm: int
    label_height_mm: int
    printer_dots_per_mm: int
    large_printer_name: str
    large_printer_model: str
    large_printer_language: str
    large_printer_mac: str
    large_printer_port: int
    large_printer_ip_override: str | None
    large_printer_print_speed: int
    large_printer_darkness: int
    large_print_enabled: bool
    large_label_width_mm: int
    large_label_height_mm: int
    large_printer_dots_per_mm: int
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
            barcode_admin_pin=os.getenv("BARCODE_ADMIN_PIN", "").strip(),
            barcode_admin_session_minutes=_int("BARCODE_ADMIN_SESSION_MINUTES", 30),
            barcode_assignment_enabled=_bool("BARCODE_ASSIGNMENT_ENABLED", False),
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
            printer_send_timeout_seconds=_int("PRINTER_SEND_TIMEOUT_SECONDS", 180),
            printer_reopen_delay_ms=_int("PRINTER_REOPEN_DELAY_MS", 250),
            printer_send_attempts=_int("PRINTER_SEND_ATTEMPTS", 3),
            printer_retry_delay_ms=_int("PRINTER_RETRY_DELAY_MS", 1000),
            printer_print_speed=_int("PRINTER_PRINT_SPEED", 2),
            printer_darkness=os.getenv("PRINTER_DARKNESS", "4A").strip().upper(),
            print_enabled=_bool("PRINT_ENABLED", False),
            label_width_mm=_int("LABEL_WIDTH_MM", 50),
            label_height_mm=_int("LABEL_HEIGHT_MM", 30),
            printer_dots_per_mm=_int("PRINTER_DOTS_PER_MM", 12),
            large_printer_name=os.getenv("LARGE_PRINTER_NAME", "zebra-large-label"),
            large_printer_model=os.getenv("LARGE_PRINTER_MODEL", "ZD421"),
            large_printer_language=os.getenv("LARGE_PRINTER_LANGUAGE", "ZPL"),
            large_printer_mac=os.getenv("LARGE_PRINTER_MAC", "60:95:32:06:E0:CF"),
            large_printer_port=_int("LARGE_PRINTER_PORT", 9100),
            large_printer_ip_override=os.getenv("LARGE_PRINTER_IP_OVERRIDE") or None,
            large_printer_print_speed=_int("LARGE_PRINTER_PRINT_SPEED", 6),
            large_printer_darkness=_int("LARGE_PRINTER_DARKNESS", 10),
            large_print_enabled=_bool("LARGE_PRINT_ENABLED", False),
            large_label_width_mm=_int("LARGE_LABEL_WIDTH_MM", 100),
            large_label_height_mm=_int("LARGE_LABEL_HEIGHT_MM", 175),
            large_printer_dots_per_mm=_int("LARGE_PRINTER_DOTS_PER_MM", 8),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
            spool_dir=Path(os.getenv("SPOOL_DIR", "/app/spool")),
        )

    @property
    def label_width_dots(self) -> int:
        return self.label_width_mm * self.printer_dots_per_mm

    @property
    def label_height_dots(self) -> int:
        return self.label_height_mm * self.printer_dots_per_mm

    def large_label_settings(self) -> "Settings":
        """Return the same application settings aimed at the large-label Zebra."""
        return replace(
            self,
            printer_name=self.large_printer_name,
            printer_model=self.large_printer_model,
            printer_language=self.large_printer_language,
            printer_mac=self.large_printer_mac,
            printer_port=self.large_printer_port,
            printer_ip_override=self.large_printer_ip_override,
            printer_print_speed=self.large_printer_print_speed,
            print_enabled=self.large_print_enabled,
            label_width_mm=self.large_label_width_mm,
            label_height_mm=self.large_label_height_mm,
            printer_dots_per_mm=self.large_printer_dots_per_mm,
        )

    def validate_runtime(self) -> list[str]:
        missing = []
        for name, value in (
            ("MYOB_USERNAME", self.myob_username),
            ("MYOB_PASSWORD", self.myob_password),
            ("DATABASE_PASSWORD", self.database_password),
            ("PRINTER_MAC", self.printer_mac),
            ("BARCODE_ADMIN_PIN", self.barcode_admin_pin),
        ):
            if not value:
                missing.append(name)
        if self.printer_print_speed not in {2, 3, 4}:
            missing.append("PRINTER_PRINT_SPEED (use 2, 3, or 4)")
        if self.printer_darkness not in {f"{level}A" for level in range(1, 6)}:
            missing.append("PRINTER_DARKNESS (use 1A through 5A)")
        if not 1 <= self.printer_send_attempts <= 10:
            missing.append("PRINTER_SEND_ATTEMPTS (use 1 through 10)")
        if not 1 <= self.printer_send_timeout_seconds <= 3600:
            missing.append("PRINTER_SEND_TIMEOUT_SECONDS (use 1 through 3600)")
        if self.printer_retry_delay_ms < 0:
            missing.append("PRINTER_RETRY_DELAY_MS (use zero or greater)")
        if not self.large_printer_mac:
            missing.append("LARGE_PRINTER_MAC")
        if self.large_printer_print_speed not in {2, 3, 4, 5, 6}:
            missing.append("LARGE_PRINTER_PRINT_SPEED (use 2 through 6)")
        if not 0 <= self.large_printer_darkness <= 30:
            missing.append("LARGE_PRINTER_DARKNESS (use 0 through 30)")
        if self.large_label_width_mm != 100 or self.large_label_height_mm != 175:
            missing.append("LARGE_LABEL dimensions (use 100 x 175 mm)")
        if self.large_printer_dots_per_mm not in {8, 12}:
            missing.append("LARGE_PRINTER_DOTS_PER_MM (use 8 or 12)")
        if self.barcode_admin_pin and (
            not self.barcode_admin_pin.isdigit()
            or not 4 <= len(self.barcode_admin_pin) <= 12
        ):
            missing.append("BARCODE_ADMIN_PIN (use 4 to 12 digits)")
        return missing
