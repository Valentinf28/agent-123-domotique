FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-websocket-client py3-pillow

COPY agent.py /opt/agent/agent.py
COPY pool_camera.py /opt/agent/pool_camera.py
COPY network_discovery.py /opt/agent/network_discovery.py
COPY connector_install.py /opt/agent/connector_install.py
COPY vendor /opt/agent/vendor
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
