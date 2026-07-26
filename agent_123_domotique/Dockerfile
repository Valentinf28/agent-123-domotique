FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-websocket-client

COPY agent.py /opt/agent/agent.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
