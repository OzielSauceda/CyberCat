#!/bin/bash
set -e

# Generate SSH host keys if missing
if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
    ssh-keygen -A
fi

# Start rsyslogd so sshd auth events land in /var/log/auth.log (Wazuh monitors this).
# Must use the daemon directly — `service rsyslog start` requires systemd which isn't in containers.
rsyslogd 2>/dev/null || true

# Start auditd (ignore failure — kernel audit may be unavailable in some environments)
service auditd start 2>/dev/null || true

# Phase 16.10: spawn conntrack -E to capture netfilter NEW events into a flat log.
# The cct-agent tails this file via the lab_logs shared volume. Wrapped in a
# subshell+|| true so a missing kernel netlink (e.g. Docker Desktop on Windows)
# doesn't abort the entrypoint.
touch /var/log/conntrack.log
chmod 644 /var/log/conntrack.log
( /usr/sbin/conntrack -E -e NEW -o timestamp -o extended -o id >> /var/log/conntrack.log 2>/dev/null & ) || true

# Configure Wazuh agent manager address
if [ -n "$WAZUH_MANAGER" ]; then
    sed -i "s/<address>.*<\/address>/<address>${WAZUH_MANAGER}<\/address>/" \
        /var/ossec/etc/ossec.conf 2>/dev/null || true
fi

# Add /var/log/auth.log monitoring if not already present (idempotent).
# Without this block, SSH auth failures are never forwarded to the manager.
if ! grep -q "auth.log" /var/ossec/etc/ossec.conf 2>/dev/null; then
    sed -i 's|</ossec_config>|  <localfile>\n    <log_format>syslog</log_format>\n    <location>/var/log/auth.log</location>\n  </localfile>\n</ossec_config>|' \
        /var/ossec/etc/ossec.conf 2>/dev/null || true
fi

# Enroll with manager using registration password
if [ -n "$WAZUH_REGISTRATION_PASSWORD" ]; then
    /var/ossec/bin/agent-auth \
        -m "${WAZUH_MANAGER:-wazuh-manager}" \
        -P "${WAZUH_REGISTRATION_PASSWORD}" \
        -A "lab-debian" 2>/dev/null || true
fi

# Start Wazuh agent
service wazuh-agent start 2>/dev/null || true

# Phase 21: launch Sandcat (Caldera's Linux agent) when CALDERA_URL is set.
# Mirrors the WAZUH_MANAGER conditional pattern above. Sandcat is fetched
# at runtime from the Caldera server's /file/download endpoint with the
# platform/architecture/group selected via headers. Wrapped in
# ( ... & ) || true so that a missing/unreachable Caldera (the common case
# when --profile caldera is OFF) does not abort sshd startup.
if [ -n "$CALDERA_URL" ]; then
    SANDCAT_GROUP="${CALDERA_GROUP:-red}"
    mkdir -p /opt/sandcat
    if [ ! -x /opt/sandcat/sandcat ]; then
        # Caldera 4.2.0's /file/download serves a precompiled or
        # on-the-fly-Go-compiled sandcat binary. Headers select the
        # variant: file=sandcat.go (the Go agent), platform=linux for
        # this container's arch. lab-debian has no depends_on for the
        # caldera service (caldera lives in its own profile), so on a
        # fresh `start.sh --profile agent --profile caldera` we race
        # caldera's startup. Retry up to 30 times (5 minutes) for the
        # binary to come back non-empty before giving up. Wrapped in
        # ( ... & ) so we don't block sshd from coming up if caldera
        # is genuinely down.
        ( for i in $(seq 1 30); do
              curl -sk -X POST \
                   -H "file:sandcat.go" \
                   -H "platform:linux" \
                   -o /opt/sandcat/sandcat.tmp \
                   "${CALDERA_URL}/file/download" 2>/dev/null
              if [ -s /opt/sandcat/sandcat.tmp ]; then
                  mv /opt/sandcat/sandcat.tmp /opt/sandcat/sandcat
                  chmod +x /opt/sandcat/sandcat
                  /opt/sandcat/sandcat -server "${CALDERA_URL}" \
                                       -group "${SANDCAT_GROUP}" \
                                       -v >> /var/log/sandcat.log 2>&1 &
                  exit 0
              fi
              rm -f /opt/sandcat/sandcat.tmp
              sleep 10
          done
          echo "sandcat fetch gave up after 5 minutes" >> /var/log/sandcat.log
        ) &
    elif [ -x /opt/sandcat/sandcat ]; then
        ( /opt/sandcat/sandcat -server "${CALDERA_URL}" \
                               -group "${SANDCAT_GROUP}" \
                               -v >> /var/log/sandcat.log 2>&1 & ) || true
    fi
fi

# Run sshd in foreground as PID 1
exec /usr/sbin/sshd -D
