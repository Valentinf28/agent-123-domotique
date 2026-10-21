"""Narrow Supervisor Wi-Fi setup. Never returns or persists credentials."""
import ipaddress
import re
import threading
import time

_LOCK = threading.Lock()
_OPERATIONS = {}

def validate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("ownerScope"), str) or not re.fullmatch(r"[a-f0-9]{64}", payload["ownerScope"]):
        raise ValueError("Reprenez la connexion depuis cette maison.")
    operation = payload.get("operation")
    fields = {"status": set(), "scan": {"interface"}, "connect": {"interface", "ssid", "password", "operationId", "confirmed"}}
    if operation not in fields or set(payload) != {"ownerScope", "operation"} | fields[operation]:
        raise ValueError("Demande Wi-Fi invalide.")
    if operation != "status" and (not isinstance(payload["interface"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", payload["interface"])):
        raise ValueError("Interface Wi-Fi invalide.")
    if operation == "connect":
        ssid, password = payload["ssid"], payload["password"]
        if payload["confirmed"] is not True or not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32 or any(ord(c) < 32 for c in ssid):
            raise ValueError("Confirmez le réseau Wi-Fi choisi.")
        if not isinstance(password, str) or not (8 <= len(password) <= 63 and all(32 <= ord(c) <= 126 for c in password) or re.fullmatch(r"[a-fA-F0-9]{64}", password)):
            raise ValueError("Vérifiez le mot de passe Wi-Fi (8 à 63 caractères ou clé hexadécimale de 64 caractères).")
        if not isinstance(payload["operationId"], str) or not re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", payload["operationId"]):
            raise ValueError("Reprenez cette connexion depuis le portail.")
    return operation

def ipv4(interface):
    result = []
    for value in (interface.get("ipv4") or {}).get("address", []):
        try:
            address = ipaddress.ip_interface(value).ip
            if address.version == 4 and not address.is_link_local and not address.is_loopback and not address.is_unspecified:
                result.append(str(address))
        except (ValueError, TypeError):
            pass
    return result

def snapshot(info):
    interfaces = info.get("interfaces", [])
    return {"ethernetConnected": any(i.get("type") == "ethernet" and i.get("connected") is True and ipv4(i) for i in interfaces),
            "interfaces": [{"interface": i["interface"], "connected": i.get("connected") is True,
                            "primary": i.get("primary") is True, "addresses": ipv4(i),
                            "ssid": ((i.get("wifi") or {}).get("ssid") or "")}
                           for i in interfaces if i.get("type") == "wireless" and isinstance(i.get("interface"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", i["interface"])]}

def command(payload, supervisor):
    operation = validate(payload)
    info = supervisor("/network/info")
    view = snapshot(info)
    if operation == "status":
        return view
    interface = next((i for i in view["interfaces"] if i["interface"] == payload["interface"]), None)
    if interface is None:
        raise ValueError("Aucun adaptateur Wi-Fi compatible trouvé sur cette box.")
    path = "/network/interface/" + interface["interface"]
    if operation == "scan":
        aps = supervisor(path + "/accesspoints").get("accesspoints", [])
        networks = {}
        for ap in aps:
            ssid = ap.get("ssid")
            if not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32:
                continue
            signal = ap.get("signal", 0)
            signal = max(0, min(100, int(signal))) if isinstance(signal, (int, float)) else 0
            auth = ap.get("auth")
            network = {"ssid": ssid, "signal": signal, "supported": auth == "wpa-psk"}
            if ssid not in networks or networks[ssid]["signal"] < signal:
                networks[ssid] = network
        return {**view, "networks": sorted(networks.values(), key=lambda n: -n["signal"])[:100]}
    # Do not change an active Wi-Fi link or cut off the sole connection.
    if not view["ethernetConnected"]:
        raise ValueError("Branchez le câble Ethernet avant de configurer le Wi-Fi.")
    if interface["connected"]:
        raise ValueError("Le Wi-Fi est déjà connecté. La modification d’un réseau actif nécessite un accompagnement.")
    key = (payload["ownerScope"], payload["operationId"])
    with _LOCK:
        now = time.monotonic()
        for old in list(_OPERATIONS):
            if now - _OPERATIONS[old] > 600:
                del _OPERATIONS[old]
        if key in _OPERATIONS:
            return {**view, "pending": True}
        if len(_OPERATIONS) >= 100:
            raise ValueError("Attendez avant de réessayer la connexion.")
        _OPERATIONS[key] = now
        try:
            supervisor(path + "/update", method="POST", payload={"enabled": True, "ipv4": {"method": "auto"},
                "wifi": {"mode": "infrastructure", "auth": "wpa-psk", "ssid": payload["ssid"], "psk": payload["password"]}}, timeout=15)
        except Exception:
            # The request may have been applied. Never automatically replay secrets.
            raise RuntimeError("Connexion non confirmée. Gardez le câble Ethernet et actualisez l’état avant de réessayer.") from None
    return {**snapshot(supervisor("/network/info")), "pending": True}
