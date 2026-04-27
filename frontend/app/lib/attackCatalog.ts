"use client"

import { useEffect, useState } from "react"
import { getAttackCatalog, type AttackEntry } from "./api"

let _promise: Promise<Map<string, AttackEntry>> | null = null

function getCatalogMap(): Promise<Map<string, AttackEntry>> {
  if (!_promise) {
    _promise = getAttackCatalog()
      .then((catalog) => new Map(catalog.entries.map((e) => [e.id, e])))
      .catch(() => new Map())
  }
  return _promise
}

export function useAttackEntry(id: string): AttackEntry | undefined {
  const [entry, setEntry] = useState<AttackEntry | undefined>(undefined)

  useEffect(() => {
    let cancelled = false
    getCatalogMap().then((map) => {
      if (!cancelled) setEntry(map.get(id))
    })
    return () => { cancelled = true }
  }, [id])

  return entry
}
