"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import * as Tooltip from "@radix-ui/react-tooltip"

const NAV = [
  {
    href: "/incidents",
    label: "Incidents",
    tip: "Your open and closed investigation cases",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
    ),
  },
  {
    href: "/detections",
    label: "Detections",
    tip: "Rules that matched suspicious activity in your event stream",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
  },
  {
    href: "/actions",
    label: "Actions",
    tip: "Actions taken, waiting to run, or pending your approval",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="11" width="18" height="5" rx="1"/>
        <path d="M8 11V7a4 4 0 0 1 8 0v4"/>
        <line x1="3" y1="20" x2="21" y2="20"/>
      </svg>
    ),
  },
  {
    href: "/lab",
    label: "Lab",
    tip: "The sandboxed lab where response actions are safely tested and observed",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
      <nav className="flex items-center gap-0.5 text-sm" aria-label="Main navigation">
        {NAV.map(({ href, label, tip, icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/")
          return (
            <Tooltip.Root key={href}>
              <Tooltip.Trigger asChild>
                <Link
                  href={href}
                  className={[
                    "flex items-center gap-1.5 rounded px-3 py-1.5 transition-colors duration-150 select-none",
                    active
                      ? "bg-dossier-paperEdge text-dossier-ink border border-dossier-evidenceTape/20"
                      : "text-dossier-ink/40 hover:bg-dossier-paperEdge hover:text-dossier-ink border border-transparent",
                  ].join(" ")}
                >
                  {icon}
                  <span className="tracking-wide">{label}</span>
                </Link>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  sideOffset={8}
                  className="z-50 max-w-[220px] rounded border border-dossier-paperEdge bg-dossier-paper px-3 py-2 text-xs leading-snug text-dossier-ink/70 shadow-xl"
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
