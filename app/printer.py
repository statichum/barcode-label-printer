from __future__ import annotations

import json
import logging
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

from .config import Settings


logger = logging.getLogger("barcode-printer")


class PrinterUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PrinterDelivery:
    ip: str
    bytes_sent: int
    bytes_total: int
    complete: bool
    attempts: int
    elapsed_seconds: float
    error: str | None = None


MAC_PATTERN = re.compile(r"^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$", re.IGNORECASE)
ARP_LINE_PATTERN = re.compile(
    r"^(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<mac>(?:[0-9a-f]{2}:){5}[0-9a-f]{2})(?:\s|$)",
    re.IGNORECASE,
)


def normalize_mac(value: str) -> str:
    normalized = value.strip().replace("-", ":").lower()
    if not MAC_PATTERN.fullmatch(normalized):
        raise ValueError("PRINTER_MAC must be a six-byte MAC address")
    return normalized


def parse_arp_scan(output: str, target_mac: str) -> str | None:
    target = normalize_mac(target_mac)
    for line in output.splitlines():
        match = ARP_LINE_PATTERN.match(line.strip())
        if match and normalize_mac(match.group("mac")) == target:
            return match.group("ip")
    return None


@dataclass
class PrinterDiscovery:
    settings: Settings

    def __post_init__(self):
        self._lock = threading.Lock()
        self._cache_path = self.settings.data_dir / "printer.json"

    def _reachable(self, ip: str) -> bool:
        try:
            with socket.create_connection(
                (ip, self.settings.printer_port),
                timeout=self.settings.printer_connect_timeout_seconds,
            ):
                return True
        except OSError:
            return False

    def _cached_ip(self) -> str | None:
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload.get("ip") if payload.get("mac") == normalize_mac(self.settings.printer_mac) else None

    def _write_cache(self, ip: str) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self._cache_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"ip": ip, "mac": normalize_mac(self.settings.printer_mac)}),
            encoding="utf-8",
        )
        temporary.replace(self._cache_path)

    def resolve(self, force_scan: bool = False) -> str:
        with self._lock:
            if self.settings.printer_ip_override:
                if self._reachable(self.settings.printer_ip_override):
                    return self.settings.printer_ip_override
                raise PrinterUnavailable(
                    f"{self.settings.printer_name} is not reachable at the configured override"
                )

            if not force_scan:
                cached = self._cached_ip()
                if cached and self._reachable(cached):
                    return cached

            try:
                result = subprocess.run(
                    [
                        "arp-scan",
                        f"--interface={self.settings.arp_interface}",
                        "--localnet",
                        "--plain",
                        "--ignoredups",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise PrinterUnavailable("Printer network discovery could not run") from exc

            if result.returncode != 0:
                detail = result.stderr.strip() or "no diagnostic output"
                raise PrinterUnavailable(
                    f"Printer network discovery failed ({result.returncode}): {detail}"
                )
            ip = parse_arp_scan(result.stdout, self.settings.printer_mac)
            if not ip:
                raise PrinterUnavailable(
                    f"{self.settings.printer_name} was not found on {self.settings.arp_interface}"
                )
            if not self._reachable(ip):
                raise PrinterUnavailable(
                    f"{self.settings.printer_name} was found at {ip}, but port {self.settings.printer_port} is closed"
                )
            self._write_cache(ip)
            return ip

    def status(self) -> dict:
        try:
            ip = self.resolve()
            return {
                "online": True,
                "name": self.settings.printer_name,
                "model": self.settings.printer_model,
                "ip": ip,
                "port": self.settings.printer_port,
                "print_enabled": self.settings.print_enabled,
            }
        except PrinterUnavailable as exc:
            return {
                "online": False,
                "name": self.settings.printer_name,
                "model": self.settings.printer_model,
                "ip": None,
                "port": self.settings.printer_port,
                "print_enabled": self.settings.print_enabled,
                "message": str(exc),
            }

    def send(self, payload: bytes) -> PrinterDelivery:
        attempts = max(1, self.settings.printer_send_attempts)
        last_error: OSError | PrinterUnavailable | None = None
        started_at = time.monotonic()
        for attempt in range(attempts):
            bytes_sent = 0
            ip = ""
            try:
                ip = self.resolve(force_scan=attempt > 0)
                self._wait_for_port_reopen()
                with socket.create_connection(
                    (ip, self.settings.printer_port),
                    timeout=self.settings.printer_connect_timeout_seconds,
                ) as connection:
                    connection.settimeout(self.settings.printer_send_timeout_seconds)
                    remaining = memoryview(payload)
                    while bytes_sent < len(payload):
                        sent = connection.send(remaining[bytes_sent:])
                        if sent <= 0:
                            raise ConnectionError(
                                "The printer connection closed during transmission"
                            )
                        bytes_sent += sent
                return PrinterDelivery(
                    ip=ip,
                    bytes_sent=bytes_sent,
                    bytes_total=len(payload),
                    complete=True,
                    attempts=attempt + 1,
                    elapsed_seconds=time.monotonic() - started_at,
                )
            except (OSError, PrinterUnavailable) as exc:
                last_error = exc
                if bytes_sent:
                    logger.error(
                        "Printer delivery became uncertain after %s of %s bytes; "
                        "the job will not be retried: %s",
                        bytes_sent,
                        len(payload),
                        exc,
                    )
                    return PrinterDelivery(
                        ip=ip,
                        bytes_sent=bytes_sent,
                        bytes_total=len(payload),
                        complete=False,
                        attempts=attempt + 1,
                        elapsed_seconds=time.monotonic() - started_at,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                logger.warning(
                    "Printer connection attempt %s of %s failed before any "
                    "print data was sent: %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
                if attempt + 1 < attempts:
                    self._wait_before_retry()

        assert last_error is not None
        raise PrinterUnavailable(
            f"The print data could not be sent after {attempts} attempts "
            f"({type(last_error).__name__}: {last_error})"
        ) from last_error

    def _wait_before_retry(self) -> None:
        time.sleep(max(0, self.settings.printer_retry_delay_ms) / 1000)

    def _wait_for_port_reopen(self) -> None:
        time.sleep(max(0, self.settings.printer_reopen_delay_ms) / 1000)
