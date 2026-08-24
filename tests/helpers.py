from pathlib import Path

from app.config import Settings


def settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "app_host": "127.0.0.1",
        "app_port": 4050,
        "myob_base_url": "https://example.invalid",
        "myob_api_root": "/entity/CustomExt/22.200.001",
        "myob_username": "test-user",
        "myob_password": "test-password",
        "myob_company": "PRV",
        "myob_verify_ssl": True,
        "myob_timeout_seconds": 10,
        "database_host": "127.0.0.1",
        "database_port": 5432,
        "database_name": "test",
        "database_user": "test",
        "database_password": "test",
        "printer_name": "sato-barcode",
        "printer_model": "CG412DT-LAN",
        "printer_language": "SBPL",
        "printer_mac": "00:19:98:84:26:F9",
        "printer_port": 9100,
        "printer_ip_override": None,
        "arp_interface": "enp5s0",
        "printer_connect_timeout_seconds": 1,
        "print_enabled": False,
        "label_width_mm": 50,
        "label_height_mm": 30,
        "printer_dots_per_mm": 12,
        "data_dir": tmp_path / "data",
        "spool_dir": tmp_path / "spool",
    }
    values.update(overrides)
    return Settings(**values)

