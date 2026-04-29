FROM debian:12-slim

ARG REALUSER_PASSWORD=lab123

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    auditd \
    conntrack \
    curl \
    gnupg \
    iptables \
    lsb-release \
    procps \
    rsyslog \
    sshpass \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Wazuh agent 4.9.2
RUN curl -sO https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/wazuh-agent_4.9.2-1_amd64.deb \
    && dpkg -i wazuh-agent_4.9.2-1_amd64.deb \
    && rm wazuh-agent_4.9.2-1_amd64.deb

# Seed lab users
RUN useradd -m -s /bin/bash realuser \
    && echo "realuser:${REALUSER_PASSWORD}" | chpasswd \
    && useradd -m -s /bin/bash baduser \
    && echo "baduser:$(cat /proc/sys/kernel/random/uuid | tr -d '-')" | chpasswd

# Create SSH host key dir and privilege separation dir
RUN mkdir -p /var/run/sshd /run/sshd \
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Auditd rules: capture EXECVE (process.created) and exit_group (process.exited)
COPY audit.rules /etc/audit/rules.d/cybercat.rules

COPY active-response/kill-process.sh /var/ossec/active-response/bin/kill-process
RUN chmod 750 /var/ossec/active-response/bin/kill-process \
    && chown root:wazuh /var/ossec/active-response/bin/kill-process

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
