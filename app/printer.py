from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
from dataclasses import dataclass

from .config import Settings


class PrinterUnavailable(RuntimeError):
    pass


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

    def send(self, payload: bytes) -> str:
        ip = self.resolve()
        try:
            with socket.create_connection(
                (ip, self.settings.printer_port),
                timeout=self.settings.printer_connect_timeout_seconds,
            ) as connection:
                connection.sendall(payload)
        except OSError:
            ip = self.resolve(force_scan=True)
            try:
                with socket.create_connection(
                    (ip, self.settings.printer_port),
                    timeout=self.settings.printer_connect_timeout_seconds,
                ) as connection:
                    connection.sendall(payload)
            except OSError as exc:
                raise PrinterUnavailable("The print data could not be sent") from exc
        return ip
