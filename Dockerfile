FROM --platform=$BUILDPLATFORM ghcr.io/linuxserver/baseimage-alpine:3.23

LABEL org.opencontainers.image.source=https://github.com/bonny1992/qbit-ops

ARG TARGETPLATFORM
ARG BUILDPLATFORM

ENV QBIT_HOST=127.0.0.1
ENV QBIT_PORT=8080
ENV QBIT_SSL=no
ENV QBIT_USER=
ENV QBIT_PASS=
ENV LOGFILE=/config/logs/space.log
ENV MIN_SPACE_GB=150
ENV DOWNLOAD_DIR=/
ENV DRY_RUN=no
ENV SET_DEBUG=no

COPY app/ /app
COPY config/ /config

RUN echo "**** install build dependencies ****" && \
    apk add --no-cache --virtual .build-deps python3-dev alpine-sdk && \
    apk add --no-cache python3 && \
    \
    echo "**** create venv and install requirements ****" && \
    python3 -m venv /lsiopy && \
    pip install -U --no-cache-dir pip setuptools wheel && \
    pip install -U --no-cache-dir \
      --find-links https://wheel-index.linuxserver.io/alpine-3.23/ \
      -r /app/requirements.txt && \
    \
    echo "**** cleanup ****" && \
    chown -R abc:abc /config /app && \
    apk del .build-deps

COPY root/ /
RUN chmod +x /etc/services.d/*/run