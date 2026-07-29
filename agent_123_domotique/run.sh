#!/bin/sh

set -eu

echo "[agent-123] Démarrage de l'Agent 1.2.3 Domotique"
exec python3 /opt/agent/agent.py
