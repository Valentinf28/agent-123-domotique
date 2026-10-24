FROM ghcr.io/home-assistant/base@sha256:992dc6a5727b97a30da8dd259b489739299c324407557df540165e2f0dbb7763
RUN apk add --no-cache python3
COPY recovery.py archive_verify.py /opt/recovery/
COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD ["/run.sh"]
