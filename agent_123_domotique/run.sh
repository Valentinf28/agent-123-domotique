#!/usr/bin/with-contenv bashio

bashio::log.info "Démarrage de l'Agent 1.2.3 Domotique"
exec python3 /opt/agent/agent.py
