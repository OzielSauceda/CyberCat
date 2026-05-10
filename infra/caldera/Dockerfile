# CyberCat: Caldera adversary-emulation server, pinned.
# Built only when --profile caldera is active. See ADR-0016.
#
# Builds Caldera 4.2.0 from upstream source. Pulling a pinned release tag
# rather than `latest` keeps the build reproducible; pulling from source
# rather than a pre-built image lets us audit every dependency in our own
# image. local.yml is copied in at build time so the first-run server
# config is deterministic.
#
# Pin rationale (2026-05-05): 5.0.0 introduced the "magma" Vue 3 UI plugin
# whose dist/assets/ directory is built via `npm run build` from source —
# the upstream Dockerfile-less install instructions assume the operator
# runs that step manually. 4.2.0 ships the older Vue UI bundled as static
# files inside plugins/, so no Node.js toolchain is needed to bring the
# server up. /api/v2 endpoints used by labs/caldera/build_operation_request.py
# exist on both lines, so the scorer is unaffected by the pin.
#
# Base image is python:3.11-slim-bookworm rather than the floating
# python:3.11-slim tag (which now resolves to Debian trixie). Caldera
# 4.2.0 pulls donut-shellcode, whose C source has implicit int/pointer
# conversions that gcc 14 (trixie default) treats as hard errors via
# -Werror=int-conversion / -Werror=incompatible-pointer-types. gcc 12
# (bookworm default) leaves them as warnings, so the build succeeds.
# donut-shellcode is a Windows-shellcode-generation dep we don't
# exercise — we drive Linux Sandcat only — so we just need it to
# compile and import without surfacing.
FROM python:3.11-slim-bookworm

ARG CALDERA_VERSION=4.2.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
# Caldera 4.2.0's requirements.txt pins websockets>=10.3 (lower-bound only),
# which lets pip resolve to websockets 16.x. The 14.0 release rewrote the
# server connection API; Caldera's app/contact/contact_websocket.py expects
# the v10/v11/v12/v13 surface, so on startup the internal /system/ready
# probe fails with code 1011 (internal error). Pinning <14 keeps Caldera
# on a compatible API.
#
# yarl is a transitive dep (aiohttp's URL parser). Somewhere between
# yarl 1.9.4 and 1.10.0 it added strict host-string validation in
# _encode_host: any ':' in a host string is rejected as invalid (callers
# are expected to split into host + port). But aiohttp 3.8.4 still passes
# `request.host` (the raw Host header, which legitimately includes
# `:port` for non-default ports) directly to URL.build(host=...) inside
# its router resolver. The result: every request whose Host header
# carries a port (i.e. all `curl http://x:8888/...` traffic) raises
# ValueError mid-resolve in yarl, and aiohttp returns a generic 500
# with no application-level log because Caldera's setup_logger silences
# everything except aiohttp.server and asyncio. Pin yarl<1.10 to keep
# the permissive host behaviour aiohttp 3.8.4 was written against.
# Confirmed locally: yarl 1.9.4 accepts URL.build(host='localhost:8888').
RUN git clone --depth 1 --branch "${CALDERA_VERSION}" --recurse-submodules \
        https://github.com/mitre/caldera.git . \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir 'websockets<14' 'yarl<1.10'

COPY local.yml conf/local.yml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888

# --insecure (in entrypoint.sh): Caldera loads conf/default.yml with its
# upstream hardcoded keys (api_key_red: ADMIN123). entrypoint.sh patches
# those keys to the runtime ${CALDERA_API_KEY} so the scorer's
# .env-sourced key agrees with the server's auth state. Acceptable
# because (a) the service is bound to 127.0.0.1 only in compose, (b) the
# server runs on the private compose bridge network, (c) the threat
# model is a single-laptop lab. ADR-0016 documents this explicitly.
ENTRYPOINT ["/entrypoint.sh"]
