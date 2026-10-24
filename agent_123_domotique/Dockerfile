FROM ghcr.io/home-assistant/base@sha256:992dc6a5727b97a30da8dd259b489739299c324407557df540165e2f0dbb7763

RUN apk add --no-cache python3 py3-websocket-client py3-pillow tzdata iproute2 py3-cryptography py3-virtualenv

COPY local_mobile.py /opt/agent/local_mobile.py
COPY local_identity.py /opt/agent/local_identity.py
COPY factory_activation.py /opt/agent/factory_activation.py
COPY factory_stage.py /opt/agent/factory_stage.py
COPY agent.py /opt/agent/agent.py
COPY automation_edit.py /opt/agent/automation_edit.py
COPY live_energy_states.py /opt/agent/live_energy_states.py
COPY wifi_setup.py /opt/agent/wifi_setup.py
COPY requirements.lock /opt/agent/requirements.lock
RUN virtualenv /opt/tuya-sdk && /opt/tuya-sdk/bin/pip install --no-cache-dir -r /opt/agent/requirements.lock && /opt/tuya-sdk/bin/pip check
ENV PATH="/opt/tuya-sdk/bin:$PATH"

COPY tuya_homes.py /opt/agent/tuya_homes.py
COPY shelly_lan.py /opt/agent/shelly_lan.py
COPY shelly_setup.py /opt/agent/shelly_setup.py
COPY lektrico_setup.py /opt/agent/lektrico_setup.py
COPY ev_discovery.py /opt/agent/ev_discovery.py
COPY equipment_setup.py /opt/agent/equipment_setup.py
COPY tuya_setup.py /opt/agent/tuya_setup.py
COPY overkiz_setup.py /opt/agent/overkiz_setup.py
COPY pool_camera.py /opt/agent/pool_camera.py
COPY network_discovery.py /opt/agent/network_discovery.py
COPY connector_install.py /opt/agent/connector_install.py
COPY vendor /opt/agent/vendor
COPY profiles /opt/agent/profiles
COPY solar_profile.py /opt/agent/solar_profile.py
COPY solar_state_wakeup.py /opt/agent/solar_state_wakeup.py
COPY solar_measurements.py /opt/agent/solar_measurements.py
COPY backup_setup.py /opt/agent/backup_setup.py
COPY installation_reset.py /opt/agent/installation_reset.py
COPY installation_update.py /opt/agent/installation_update.py
COPY update_recovery.py /opt/agent/update_recovery.py
COPY ddzy422_setup.py /opt/agent/ddzy422_setup.py
COPY ddzy422_activation.py /opt/agent/ddzy422_activation.py
COPY micro_setup.py /opt/agent/micro_setup.py
COPY local_solar_measurements.py /opt/agent/local_solar_measurements.py
COPY integrations /opt/agent/integrations
COPY deye_topology.py /opt/agent/deye_topology.py
COPY solar_identity.py /opt/agent/solar_identity.py
COPY solar_recovery.py /opt/agent/solar_recovery.py
COPY solar_setup.py /opt/agent/solar_setup.py
COPY site_location.py /opt/agent/site_location.py
COPY solar_activation.py /opt/agent/solar_activation.py
COPY config.yaml /opt/agent/config.yaml
COPY release_smoke.py /opt/agent/release_smoke.py
COPY package-manifest.json /opt/agent/package-manifest.json
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
