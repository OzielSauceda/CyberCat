import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        dossier: {
          paper:       "#060a0f",   // deep cyber black — main bg
          paperEdge:   "#0c1b2e",   // dark navy — borders, surfaces
          ink:         "#e0eaf3",   // cool blue-gray — primary text
          redaction:   "#ff2d55",   // critical red neon
          evidenceTape:"#00d4ff",   // primary cyan neon — accent
          stamp:       "#030d1a",   // deepest dark — inner surfaces
        },
        cyber: {
          green:  "#00ff9f",
          orange: "#ff6b35",
          yellow: "#fbbf24",
          muted:  "#2a4a66",
        },
      },
      fontFamily: {
        sans: ["var(--font-barlow)", "Barlow", "system-ui", "sans-serif"],
        case: ["var(--font-rajdhani)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        dossier: "0 0 0 1px rgba(0,212,255,0.07), 0 4px 24px rgba(0,0,0,0.7)",
      },
      backgroundImage: {
        foldermark:
          "repeating-linear-gradient(0deg, transparent, transparent 40px, rgba(0,212,255,0.018) 40px, rgba(0,212,255,0.018) 41px)",
      },
    },
  },
  plugins: [],
}

export default config
