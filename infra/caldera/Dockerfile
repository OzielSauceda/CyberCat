# CyberCat: Caldera adversary-emulation server, pinned.
# Built only when --profile caldera is active. See ADR-0016.
#
# Builds Caldera 5.0.0 from upstream source. Pulling a pinned release tag
# rather than `latest` keeps the build reproducible; pulling from source
# rather than a pre-built image lets us audit every dependency in our own
# image. local.yml is copied in at build time so the first-run server
# config is deterministic.
FROM python:3.11-slim

ARG CALDERA_VERSION=5.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
RUN git clone --depth 1 --branch "${CALDERA_VERSION}" --recurse-submodules \
        https://github.com/mitre/caldera.git . \
    && pip install --no-cache-dir -r requirements.txt

COPY local.yml conf/local.yml

EXPOSE 8888

# --insecure: skips Caldera's TLS bootstrap. Acceptable here because (a)
# the service is bound to 127.0.0.1 only in compose, (b) the server runs
# on the private compose bridge network, (c) the threat model is a single
# laptop lab. ADR-0016 documents this explicitly.
CMD ["python3", "server.py", "--insecure"]
