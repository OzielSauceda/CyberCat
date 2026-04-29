// Central token map — components use these class-name strings instead of hardcoded hex.
// Tailwind colours are defined in tailwind.config.ts under theme.extend.colors.dossier.

export const DOSSIER = {
  bg: {
    paper: "bg-dossier-paper",
    paperEdge: "bg-dossier-paperEdge",
    stamp: "bg-dossier-stamp",
  },
  text: {
    ink: "text-dossier-ink",
    redaction: "text-dossier-redaction",
    evidenceTape: "text-dossier-evidenceTape",
    stamp: "text-dossier-stamp",
  },
  border: {
    paper: "border-dossier-paper",
    paperEdge: "border-dossier-paperEdge",
    evidenceTape: "border-dossier-evidenceTape",
    redaction: "border-dossier-redaction",
  },
  shadow: "shadow-dossier",
  font: "font-case",
  bg_image: "bg-foldermark",
} as const

export type DossierBg = (typeof DOSSIER.bg)[keyof typeof DOSSIER.bg]
export type DossierText = (typeof DOSSIER.text)[keyof typeof DOSSIER.text]
export type DossierBorder = (typeof DOSSIER.border)[keyof typeof DOSSIER.border]
