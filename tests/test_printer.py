import socket
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
    connection.send.return_value = len(b"label")
    context = MagicMock()
    context.__enter__.return_value = connection

    with (
        patch.object(discovery, "resolve", return_value="10.10.1.16"),
        patch("app.printer.time.sleep") as sleep,
        patch("app.printer.socket.create_connection", return_value=context),
    ):
        delivery = discovery.send(b"label")

    sleep.assert_called_once_with(0.25)
    assert delivery.ip == "10.10.1.16"
    assert delivery.complete is True
    assert delivery.bytes_sent == len(b"label")
    connection.settimeout.assert_called_once_with(180)
    connection.send.assert_called_once()


def test_send_rediscovers_and_retries_when_printer_port_is_temporarily_closed(tmp_path):
    discovery = PrinterDiscovery(settings(tmp_path))
    connection = MagicMock()
    connection.send.return_value = len(b"label")
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
        delivery = discovery.send(b"label")

    assert resolve.call_args_list == [call(force_scan=False), call(force_scan=True)]
    assert sleep.call_args_list == [call(1.0), call(0.25)]
    assert delivery.complete is True
    connection.send.assert_called_once()


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


def test_send_never_retries_a_job_after_any_bytes_were_accepted(tmp_path):
    discovery = PrinterDiscovery(settings(tmp_path))
    connection = MagicMock()
    connection.send.side_effect = [2, socket.timeout("timed out")]
    context = MagicMock()
    context.__enter__.return_value = connection

    with (
        patch.object(discovery, "resolve", return_value="10.10.1.16") as resolve,
        patch("app.printer.time.sleep") as sleep,
        patch("app.printer.socket.create_connection", return_value=context),
    ):
        delivery = discovery.send(b"label")

    assert delivery.complete is False
    assert delivery.bytes_sent == 2
    assert delivery.bytes_total == 5
    assert delivery.attempts == 1
    assert delivery.error == "TimeoutError: timed out"
    resolve.assert_called_once_with(force_scan=False)
    sleep.assert_called_once_with(0.25)
    assert connection.send.call_count == 2


def test_send_retries_when_timeout_happens_before_any_bytes_are_sent(tmp_path):
    discovery = PrinterDiscovery(settings(tmp_path))
    first_connection = MagicMock()
    first_connection.send.side_effect = socket.timeout("timed out")
    first_context = MagicMock()
    first_context.__enter__.return_value = first_connection
    second_connection = MagicMock()
    second_connection.send.return_value = len(b"label")
    second_context = MagicMock()
    second_context.__enter__.return_value = second_connection

    with (
        patch.object(discovery, "resolve", return_value="10.10.1.16") as resolve,
        patch("app.printer.time.sleep") as sleep,
        patch(
            "app.printer.socket.create_connection",
            side_effect=[first_context, second_context],
        ),
    ):
        delivery = discovery.send(b"label")

    assert delivery.complete is True
    assert delivery.attempts == 2
    assert resolve.call_args_list == [call(force_scan=False), call(force_scan=True)]
    assert sleep.call_args_list == [call(0.25), call(1.0), call(0.25)]
