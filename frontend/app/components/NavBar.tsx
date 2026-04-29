"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import * as Tooltip from "@radix-ui/react-tooltip"

const NAV = [
  {
    href: "/incidents",
    label: "Incidents",
    tip: "Open and closed cases — each one is a story of related signals.",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
    ),
  },
  {
    href: "/detections",
    label: "Detections",
    tip: "Rules that matched suspicious activity. Every match is a clue.",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
  },
  {
    href: "/actions",
    label: "Actions",
    tip: "Things CyberCat did, will do, or is waiting on you to approve.",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="11" width="18" height="5" rx="1"/>
        <path d="M8 11V7a4 4 0 0 1 8 0v4"/>
        <line x1="3" y1="20" x2="21" y2="20"/>
      </svg>
    ),
  },
  {
    href: "/lab",
    label: "Lab",
    tip: "Sandboxed environment where response actions run safely without touching real systems.",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 3h6"/>
        <path d="M9 3v5.5L4.5 17A2 2 0 0 0 6.28 20h11.44a2 2 0 0 0 1.78-2.95L15 8.5V3"/>
      </svg>
    ),
  },
]

export default function NavBar() {
  const pathname = usePathname()

  return (
    <Tooltip.Provider delayDuration={450} skipDelayDuration={100}>
      <nav className="flex h-full" aria-label="Main navigation">
        {NAV.map(({ href, label, tip, icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/")
          return (
            <Tooltip.Root key={href}>
              <Tooltip.Trigger asChild>
                <Link
                  href={href}
                  className={[
                    "nav-link relative flex items-center gap-2 px-4 font-case text-[12px] tracking-[0.12em] uppercase select-none transition-all duration-150",
                    "after:content-[''] after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:transition-colors after:duration-150",
                    active
                      ? "text-dossier-evidenceTape after:bg-dossier-evidenceTape"
                      : "text-dossier-ink/65 hover:text-dossier-ink hover:bg-white/[0.025] after:bg-transparent",
                  ].join(" ")}
                >
                  <span className={active ? "" : "opacity-75"}>{icon}</span>
                  <span className="nav-rainbow-label">{label}</span>
                </Link>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  sideOffset={8}
                  className="z-50 max-w-[220px] rounded border border-dossier-paperEdge bg-dossier-stamp px-3 py-2 text-xs leading-snug text-dossier-ink shadow-xl"
                >
                  {tip}
                  <Tooltip.Arrow className="fill-dossier-paperEdge" />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
          )
        })}
      </nav>
    </Tooltip.Provider>
  )
}
