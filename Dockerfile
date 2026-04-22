ARG BASE_VERSION=2026.4.1
FROM esphome/esphome:${BASE_VERSION}

# Copy enhanced dashboard overlay files
COPY overrides/const.py /esphome/esphome/dashboard/const.py
COPY overrides/core.py /esphome/esphome/dashboard/core.py
COPY overrides/models.py /esphome/esphome/dashboard/models.py
COPY overrides/web_server.py /esphome/esphome/dashboard/web_server.py
COPY overrides/status/ping.py /esphome/esphome/dashboard/status/ping.py
COPY overrides/templates/ /esphome/esphome/dashboard/templates/
