FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-websocket-client py3-pillow tzdata iproute2 py3-cryptography

COPY local_identity.py /opt/agent/local_identity.py
COPY agent.py /opt/agent/agent.py
COPY pool_camera.py /opt/agent/pool_camera.py
COPY network_discovery.py /opt/agent/network_discovery.py
COPY connector_install.py /opt/agent/connector_install.py
COPY vendor /opt/agent/vendor
COPY profiles /opt/agent/profiles
COPY solar_profile.py /opt/agent/solar_profile.py
COPY solar_measurements.py /opt/agent/solar_measurements.py
COPY backup_setup.py /opt/agent/backup_setup.py
COPY solar_identity.py /opt/agent/solar_identity.py
COPY solar_recovery.py /opt/agent/solar_recovery.py
COPY solar_setup.py /opt/agent/solar_setup.py
COPY site_location.py /opt/agent/site_location.py
COPY solar_activation.py /opt/agent/solar_activation.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
