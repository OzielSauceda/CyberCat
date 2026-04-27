import type { ActionKind, LabAssetKind } from "./api"

type FieldKind = "text" | "select" | "select-lab-asset"

export interface FieldDef {
  name: string
  label: string
  kind: FieldKind
  required?: boolean
  options?: { value: string; label: string }[]
  labAssetKind?: LabAssetKind
  placeholder?: string
  help?: string
}

export interface ActionFormDef {
  label: string
  enabled: boolean
  fields: FieldDef[]
  buildParams: (form: Record<string, string>) => Record<string, unknown>
}

export const ACTION_FORMS: Record<ActionKind, ActionFormDef> = {
  tag_incident: {
    label: "Tag incident",
    enabled: true,
    fields: [
      {
        name: "tag",
        label: "Tag",
        kind: "text",
        required: true,
        placeholder: "e.g. identity-compromise-chain",
      },
    ],
    buildParams: ({ tag }) => ({ tag }),
  },
  elevate_severity: {
    label: "Elevate severity",
    enabled: true,
    fields: [
      {
        name: "to",
        label: "New severity",
        kind: "select",
        required: true,
        options: [
          { value: "low", label: "Low" },
          { value: "medium", label: "Medium" },
          { value: "high", label: "High" },
          { value: "critical", label: "Critical" },
        ],
      },
    ],
    buildParams: ({ to }) => ({ to }),
  },
  flag_host_in_lab: {
    label: "Flag host in lab",
    enabled: true,
    fields: [
      {
        name: "host",
        label: "Lab host",
        kind: "select-lab-asset",
        labAssetKind: "host",
        required: true,
        placeholder: "e.g. lab-win10-01",
        help: "Must be registered in lab_assets",
      },
    ],
    buildParams: ({ host }) => ({ host }),
  },
  quarantine_host_lab: {
    label: "Quarantine host",
    enabled: true,
    fields: [
      {
        name: "host",
        label: "Lab host",
        kind: "select-lab-asset",
        labAssetKind: "host",
        required: true,
        help: "Host will be marked quarantined in lab_assets",
      },
    ],
    buildParams: ({ host }) => ({ host }),
  },
  invalidate_lab_session: {
    label: "Invalidate lab session",
    enabled: true,
    fields: [
      {
        name: "user",
        label: "User",
        kind: "select-lab-asset",
        labAssetKind: "user",
        required: true,
      },
      {
        name: "host",
        label: "Host",
        kind: "select-lab-asset",
        labAssetKind: "host",
        required: true,
      },
    ],
    buildParams: ({ user, host }) => ({ user, host }),
  },
  block_observable: {
    label: "Block observable",
    enabled: true,
    fields: [
      {
        name: "kind",
        label: "Kind",
        kind: "select",
        required: true,
        options: [
          { value: "ip", label: "IP Address" },
          { value: "domain", label: "Domain" },
          { value: "hash", label: "File Hash" },
          { value: "file", label: "File Path" },
        ],
      },
      {
        name: "value",
        label: "Value",
        kind: "text",
        required: true,
        placeholder: "e.g. 192.168.1.100",
      },
    ],
    buildParams: ({ kind, value }) => ({ kind, value }),
  },
  kill_process_lab: {
    label: "Kill process",
    enabled: true,
    fields: [
      {
        name: "host",
        label: "Lab host",
        kind: "select-lab-asset",
        labAssetKind: "host",
        required: true,
      },
      {
        name: "pid",
        label: "PID",
        kind: "text",
        required: true,
        placeholder: "e.g. 1234",
      },
      {
        name: "process_name",
        label: "Process name",
        kind: "text",
        required: false,
        placeholder: "e.g. powershell.exe",
      },
    ],
    buildParams: ({ host, pid, process_name }) => ({
      host,
      pid: parseInt(pid, 10) || 0,
      process_name: process_name || "",
    }),
  },
  request_evidence: {
    label: "Request evidence",
    enabled: true,
    fields: [
      {
        name: "evidence_kind",
        label: "Evidence type",
        kind: "select",
        required: true,
        options: [
          { value: "triage_log", label: "Triage log" },
          { value: "process_list", label: "Process list" },
          { value: "network_connections", label: "Network connections" },
          { value: "memory_snapshot", label: "Memory snapshot" },
        ],
      },
      {
        name: "target_host",
        label: "Target host (optional)",
        kind: "select-lab-asset",
        labAssetKind: "host",
        required: false,
      },
    ],
    buildParams: ({ evidence_kind, target_host }) => ({
      evidence_kind,
      ...(target_host ? { target_host } : {}),
    }),
  },
}

export const ENABLED_KINDS = (Object.keys(ACTION_FORMS) as ActionKind[]).filter(
  (k) => ACTION_FORMS[k].enabled,
)
