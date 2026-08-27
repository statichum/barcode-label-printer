from unittest.mock import MagicMock, call, patch

import pytest

from app.printer import (
    PrinterDiscovery,
    PrinterUnavailable,
    normalize_mac,
    parse_arp_scan,
)
from tests.helpers import settings


ARP_OUTPUT = """
10.10.1.16\t00:19:98:84:26:f9\tSato
10.10.1.26\t60:95:32:06:e0:cf\tUnknown
"""


def test_parse_arp_scan_matches_configured_mac():
    assert parse_arp_scan(ARP_OUTPUT, "00:19:98:84:26:F9") == "10.10.1.16"


def test_parse_arp_scan_does_not_confuse_zebra():
    assert parse_arp_scan(ARP_OUTPUT, "60:95:32:06:E0:CF") == "10.10.1.26"


def test_mac_normalization_and_validation():
    assert normalize_mac("00-19-98-84-26-F9") == "00:19:98:84:26:f9"
    with pytest.raises(ValueError):
        normalize_mac("not-a-mac")


def test_send_waits_before_reopening_cg4_port(tmp_path):
    discovery = PrinterDiscovery(settings(tmp_path))
    connection = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = connection

    with (
        patch.object(discovery, "resolve", return_value="10.10.1.16"),
        patch("app.printer.time.sleep") as sleep,
        patch("app.printer.socket.create_connection", return_value=context),
    ):
        assert discovery.send(b"label") == "10.10.1.16"

    sleep.assert_called_once_with(0.25)
    connection.sendall.assert_called_once_with(b"label")


def test_send_rediscovers_and_retries_when_printer_port_is_temporarily_closed(tmp_path):
    discovery = PrinterDiscovery(settings(tmp_path))
    connection = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = connection

    with (
        patch.object(
            discovery,
            "resolve",
            side_effect=[
                PrinterUnavailable("printer was found, but port 9100 is closed"),
                "10.10.1.16",
            ],
        ) as resolve,
        patch("app.printer.time.sleep") as sleep,
        patch("app.printer.socket.create_connection", return_value=context),
    ):
        assert discovery.send(b"label") == "10.10.1.16"

    assert resolve.call_args_list == [call(force_scan=False), call(force_scan=True)]
    assert sleep.call_args_list == [call(1.0), call(0.25)]
    connection.sendall.assert_called_once_with(b"label")


def test_send_reports_failure_only_after_all_discovery_attempts(tmp_path):
    discovery = PrinterDiscovery(settings(tmp_path))
    unavailable = PrinterUnavailable("port 9100 is closed")

    with (
        patch.object(discovery, "resolve", side_effect=unavailable) as resolve,
        patch("app.printer.time.sleep") as sleep,
    ):
        with pytest.raises(PrinterUnavailable, match="after 3 attempts"):
            discovery.send(b"label")

    assert resolve.call_args_list == [
        call(force_scan=False),
        call(force_scan=True),
        call(force_scan=True),
    ]
    assert sleep.call_args_list == [call(1.0), call(1.0)]
