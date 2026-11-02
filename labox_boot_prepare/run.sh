#!/usr/bin/with-contenv sh
set -eu
exec unshare --net -- python3 /opt/boot/worker.py
