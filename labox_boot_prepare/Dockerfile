FROM ghcr.io/home-assistant/base@sha256:992dc6a5727b97a30da8dd259b489739299c324407557df540165e2f0dbb7763
RUN apk add --no-cache python3 util-linux
COPY boot.py worker.py /opt/boot/
COPY run.sh /run.sh
RUN chmod 755 /run.sh
CMD ["/run.sh"]
COPY config.yaml apparmor.txt README.md manifest.json .dockerignore Dockerfile /opt/proof/
COPY run.sh /opt/proof/run.sh
