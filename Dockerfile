FROM lsiobase/alpine:3.11

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

