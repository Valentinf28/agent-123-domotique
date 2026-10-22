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
        # Fixtures must not discover or scan the CI runner's real interfaces.
        adapters = patch.object(discovery, 'current_adapters', side_effect=lambda fallback: fallback)
        adapters.start()
        self.addCleanup(adapters.stop)

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

class NeighborTests(unittest.TestCase):
    def test_exact_local_mac_does_not_claim_solar_or_integration(self):
        i=ipaddress.IPv4Interface("192.168.6.181/24")
        rows=[{"dst":"192.168.6.180","lladdr":"88:a6:8d:44:e6:ce","state":["REACHABLE"]},{"dst":"192.168.7.180","lladdr":"88:a6:8d:44:e6:ce","state":["REACHABLE"]},{"dst":"192.168.6.182","lladdr":"00:22:33:44:55:66","state":["REACHABLE"]}]
        result=discovery.matching_neighbors(rows,[i],"88:a6:8d:44:e6:ce")
        self.assertEqual(len(result),1);self.assertEqual(result[0]["host"],"192.168.6.180");self.assertEqual(result[0]["status"],"network_only");self.assertFalse(result[0]["integrated"]);self.assertNotIn("loggerSerial",result[0]);self.assertNotIn("connector",result[0])
    def test_failed_neighbors_own_address_and_large_subnets_rejected(self):
        row={"dst":"192.168.6.180","lladdr":"88:a6:8d:44:e6:ce","state":["FAILED"]};i=ipaddress.IPv4Interface("192.168.6.181/24")
        self.assertEqual(discovery.matching_neighbors([row],[i],row["lladdr"]),[])
        row["state"]=["REACHABLE"];self.assertEqual(discovery.matching_neighbors([row],[ipaddress.IPv4Interface("192.168.6.180/24")],row["lladdr"]),[])
        self.assertEqual(discovery.matching_neighbors([row],[ipaddress.IPv4Interface("192.168.6.181/16")],row["lladdr"]),[])
    def test_rejects_target_injection_and_marks_conflicting_addresses_ambiguous(self):
        for mac in ("../x","88:a6:8d:44:e6:ce; reboot","ff:ff:ff:ff:ff:ff",{}):
            with self.assertRaises(ValueError):discovery.normalized_target_mac(mac)
        rows=[{"dst":ip,"lladdr":"88:a6:8d:44:e6:ce","state":["REACHABLE"]} for ip in ["192.168.6.180","192.168.6.182"]]
        self.assertTrue(all(d["status"]=="ambiguous" for d in discovery.matching_neighbors(rows,[ipaddress.IPv4Interface("192.168.6.181/24")],"88:a6:8d:44:e6:ce")))
