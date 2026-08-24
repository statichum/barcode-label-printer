import pytest

from app.printer import normalize_mac, parse_arp_scan


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

