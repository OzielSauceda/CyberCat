from __future__ import annotations

# Maps Sigma field names → Event.normalized dict keys.
# Only fields we actually normalize are listed; unknown fields cause a skip at compile time.
SIGMA_TO_NORMALIZED: dict[str, str] = {
    # process_creation
    "Image": "image",
    "CommandLine": "cmdline",
    "ParentImage": "parent_image",
    "ParentCommandLine": "parent_cmdline",
    "User": "user",
    # authentication / network
    "SourceIp": "source_ip",
    "SrcIp": "src_ip",
    "DestinationIp": "dst_ip",
    "DstIp": "dst_ip",
    "DestinationPort": "dst_port",
    "DstPort": "dst_port",
    "LogonType": "auth_type",
    # network_connection
    "Initiated": "initiated",
    "Protocol": "proto",
    # host field present on most events
    "ComputerName": "host",
    "Workstation": "host",
}

# Maps Sigma logsource.category to our canonical event.kind(s).
CATEGORY_TO_KINDS: dict[str, list[str]] = {
    "process_creation": ["process.created"],
    "authentication": ["auth.succeeded", "auth.failed"],
    "network_connection": ["network.connection"],
    "file_event": ["file.created"],
}


def map_field(sigma_field: str) -> str | None:
    """Return the normalized key for a Sigma field name, or None if unmapped."""
    return SIGMA_TO_NORMALIZED.get(sigma_field)


def kinds_for_category(category: str | None) -> list[str]:
    """Return the event.kind values that correspond to a Sigma logsource category."""
    if category is None:
        return []
    return CATEGORY_TO_KINDS.get(category, [])
