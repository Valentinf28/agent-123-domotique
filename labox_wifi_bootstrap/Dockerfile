FROM ghcr.io/home-assistant/base@sha256:992dc6a5727b97a30da8dd259b489739299c324407557df540165e2f0dbb7763
RUN apk add --no-cache python3 py3-pip py3-virtualenv dnsmasq iptables iproute2 \
 && python3 -m venv /opt/wifi-venv
COPY requirements.lock /opt/wifi/requirements.lock
RUN /opt/wifi-venv/bin/pip install --no-cache-dir --require-hashes -r /opt/wifi/requirements.lock
COPY *.py /opt/wifi/
COPY web /opt/wifi/web
COPY config.yaml /opt/wifi/config.yaml
COPY run.sh /run.sh
RUN chmod 755 /run.sh
CMD ["/run.sh"]
COPY manifest.json /opt/wifi/manifest.json
COPY run.sh /opt/wifi/run.sh
COPY Dockerfile /opt/wifi/Dockerfile
COPY README.md /opt/wifi/README.md
COPY .dockerignore /opt/wifi/.dockerignore
