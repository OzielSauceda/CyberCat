import type { Metadata } from "next"
import Link from "next/link"
import "./globals.css"
import { ToastProvider } from "./components/Toast"
import StreamStatusBadge from "./components/StreamStatusBadge"
import UserBadge from "./components/UserBadge"
import WazuhBridgeBadge from "./components/WazuhBridgeBadge"
import { SessionProvider } from "./lib/SessionContext"

export const metadata: Metadata = {
  title: {
    default: "CyberCat",
    template: "%s — CyberCat",
  },
  description: "Threat-informed automated incident response platform",
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
        <SessionProvider>
          <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
            <div className="mx-auto flex h-12 max-w-screen-xl items-center gap-6 px-4">
              <Link
                href="/incidents"
                className="flex items-center gap-2 font-semibold tracking-tight text-zinc-100 hover:text-white"
              >
                <span className="text-indigo-400 font-bold text-lg">[CC]</span>
                <span>CyberCat</span>
              </Link>
              <nav className="flex items-center gap-1 text-sm">
                <Link
                  href="/incidents"
                  className="rounded px-3 py-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                >
                  Incidents
                </Link>
                <Link
                  href="/detections"
                  className="rounded px-3 py-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                >
                  Detections
                </Link>
                <Link
                  href="/actions"
                  className="rounded px-3 py-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                >
                  Actions
                </Link>
                <Link
                  href="/lab"
                  className="rounded px-3 py-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                >
                  Lab
                </Link>
              </nav>
              <div className="ml-auto flex items-center gap-2">
                <StreamStatusBadge />
                <UserBadge />
                <WazuhBridgeBadge />
              </div>
            </div>
          </header>
          <ToastProvider>
            <main className="mx-auto max-w-screen-xl px-4 py-6">
              {children}
            </main>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  )
}
