FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
RUN python -m pip install --no-cache-dir 'homeassistant==2026.10.1'
RUN python -c "import sys, importlib.metadata; assert sys.version_info >= (3,14,2); assert importlib.metadata.version('homeassistant') == '2026.10.1'"
ENV LABOX_REAL_HA_ISOLATED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /candidate
CMD ["python", "tests/real_ha_202610/check_native.py"]
