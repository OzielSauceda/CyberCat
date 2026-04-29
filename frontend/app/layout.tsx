import type { Metadata } from "next"
import { Rajdhani } from "next/font/google"
import Link from "next/link"
import "./globals.css"
import { ToastProvider } from "./components/Toast"
import StreamStatusBadge from "./components/StreamStatusBadge"
import UserBadge from "./components/UserBadge"
import WazuhBridgeBadge from "./components/WazuhBridgeBadge"
import NavBar from "./components/NavBar"
import HelpMenu from "./components/HelpMenu"
import CaseBoard from "./components/CaseBoard"
import DemoDataBanner from "./components/DemoDataBanner"
import { FirstRunTour } from "./components/FirstRunTour"
import { SessionProvider } from "./lib/SessionContext"

const rajdhani = Rajdhani({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-rajdhani",
  display: "swap",
})

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
    <html lang="en" className={`dark ${rajdhani.variable}`}>
      <body className="min-h-screen bg-dossier-paper text-dossier-ink antialiased">
        <SessionProvider>
          <header className="sticky top-0 z-50 border-b border-dossier-paperEdge bg-dossier-paper/95 backdrop-blur-sm">
            <div className="mx-auto flex h-12 max-w-screen-xl items-center gap-5 px-4">

              {/* Logotype */}
              <Link href="/" className="flex shrink-0 items-baseline gap-1.5 font-case transition-opacity hover:opacity-80">
                <span className="text-sm font-normal tracking-widest text-dossier-evidenceTape">
                  CYBERCAT
                </span>
                <span className="text-xs text-dossier-ink/25">//</span>
                <span className="text-[11px] uppercase tracking-[0.2em] text-dossier-ink/40">
                  Case Board
                </span>
                <span
                  className="ml-0.5 inline-block text-[11px] text-dossier-evidenceTape/45"
                  style={{ animation: "cursor-blink 1.1s step-end infinite" }}
                >
                  ▋
                </span>
              </Link>

              {/* Divider */}
              <div className="h-4 w-px bg-dossier-paperEdge" />

              {/* Navigation */}
              <NavBar />

              {/* Right: operator credentials + help */}
              <div className="ml-auto flex items-center gap-2">
                <StreamStatusBadge />
                <WazuhBridgeBadge />
                <UserBadge />
                <div className="h-4 w-px bg-dossier-paperEdge" />
                <HelpMenu />
              </div>

            </div>
          </header>

          <ToastProvider>
            <DemoDataBanner />
            <main className="mx-auto max-w-screen-xl px-4 py-6">
              <CaseBoard>
                {children}
              </CaseBoard>
            </main>
            <FirstRunTour />
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  )
}
