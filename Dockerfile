FROM --platform=$BUILDPLATFORM lsiobase/alpine:3.11

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

RUN echo "**** install dependencies ****" && \
    apk add --no-cache python3 python3-dev alpine-sdk && \
    \
    echo "**** install pip ****" && \
    python3 -m ensurepip && \
    rm -r /usr/lib/python*/ensurepip && \
    pip3 install --no-cache --upgrade pip setuptools wheel && \
    if [ ! -e /usr/bin/python ]; then ln -sf python3 /usr/bin/python ; fi && \
    if [ ! -e /usr/bin/pip ]; then ln -s pip3 /usr/bin/pip ; fi
    
COPY app/ /app
COPY config/ /config

RUN chown -R abc:abc /config && \
    pip install -r /app/requirements.txt && \
    apk del python3-dev alpine-sdk


COPY root/ /

