import importlib.util
import ipaddress
from pathlib import Path
import unittest
from unittest.mock import patch
import socket

spec = importlib.util.spec_from_file_location("discovery", Path(__file__).parents[1] / "agent_123_domotique/network_discovery.py")
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.interface = ipaddress.IPv4Interface("192.168.6.115/24")

    def test_logger_identity_and_found_does_not_mean_integrated(self):
        result = discovery.parse_reply(b"192.168.6.178,D42787140716,2974839220", "192.168.6.178", self.interface)
        self.assertEqual(result["mac"], "d4:27:87:14:07:16")
        self.assertEqual(result["loggerSerial"], 2974839220)
        self.assertFalse(result["integrated"])
        self.assertEqual(result["status"], "found")

    def test_rejects_spoofed_foreign_and_invalid_packets(self):
        for data, sender in [
            (b"192.168.6.178,D42787140716,2974839220", "192.168.6.66"),
            (b"192.168.7.178,D42787140716,2974839220", "192.168.7.178"),
            (b"192.168.6.255,D42787140716,2974839220", "192.168.6.255"),
            (b"192.168.6.178,FFFFFFFFFFFF,2974839220", "192.168.6.178"),
            (b"192.168.6.178,D42787140716,4294967296", "192.168.6.178"),
            (b"192.168.6.178,D42787140716,-1", "192.168.6.178"),
            (b"\xff" * 10, "192.168.6.178"),
            (b"a" * 257, "192.168.6.178"),
        ]:
            with self.subTest(data=data):
                self.assertIsNone(discovery.parse_reply(data, sender, self.interface))

    def test_only_enabled_private_interfaces_and_no_public_broadcast(self):
        adapters = [{"enabled": True, "ipv4": [
            {"address": address, "network_prefix": prefix} for address, prefix in
            [("192.168.6.115", 24), ("192.168.6.115", 24), ("8.8.8.8", 24),
             ("127.0.0.1", 8), ("169.254.1.1", 16), ("10.0.0.1", 0)]
        ]}, {"enabled": False, "ipv4": [{"address": "10.1.1.1", "network_prefix": 24}]}]
        self.assertEqual(discovery.local_interfaces(adapters), [self.interface])

    def test_empty_network_is_explicit_error(self):
        with self.assertRaisesRegex(RuntimeError, "Aucun réseau"):
            discovery.discover_solarman([])

    def test_tcp_only_device_remains_unidentified(self):
        adapters = [{"enabled": True, "ipv4": [{"address": "192.168.6.1", "network_prefix": 30}]}]
        with patch.object(discovery.socket, "socket") as udp, patch.object(discovery.socket, "create_connection") as tcp:
            udp.return_value.__enter__.return_value.recvfrom.side_effect = socket.timeout
            result = discovery.discover_solarman(adapters)
        self.assertEqual(len(result["devices"]), 1)
        self.assertEqual(result["devices"][0]["status"], "unidentified")
        self.assertNotIn("connector", result["devices"][0])
        self.assertFalse(result["devices"][0]["integrated"])
        tcp.assert_called_once_with(("192.168.6.2", 8899), timeout=0.2, source_address=("192.168.6.1", 0))

    def test_no_unbounded_port_scan_on_large_network(self):
        adapters = [{"enabled": True, "ipv4": [{"address": "10.0.0.1", "network_prefix": 8}]}]
        with patch.object(discovery.socket, "socket") as udp, patch.object(discovery.socket, "create_connection") as tcp:
            udp.return_value.__enter__.return_value.recvfrom.side_effect = socket.timeout
            result = discovery.discover_solarman(adapters)
        tcp.assert_not_called()
        self.assertTrue(result["warnings"])

    def test_failed_network_is_not_successful_empty_discovery(self):
        with patch.object(discovery.socket, "socket", side_effect=OSError("unreachable")):
            with self.assertRaisesRegex(RuntimeError, "ne peut pas rechercher"):
                discovery.discover_solarman([{"enabled": True, "ipv4": [{"address": "192.168.6.1", "network_prefix": 24}]}])
