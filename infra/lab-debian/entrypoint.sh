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

# Run sshd in foreground as PID 1
exec /usr/sbin/sshd -D
