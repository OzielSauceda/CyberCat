export default function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 200"
      className={className}
      aria-label="CyberCat"
      role="img"
    >
      <defs>
        {/* Warm orange fur — bright center, rich at edges */}
        <radialGradient id="ccFur" cx="44%" cy="34%" r="66%">
          <stop offset="0%"   stopColor="#ffc040" />
          <stop offset="55%"  stopColor="#e88520" />
          <stop offset="100%" stopColor="#b85010" />
        </radialGradient>

        {/* Amber iris */}
        <radialGradient id="ccIris" cx="34%" cy="32%" r="68%">
          <stop offset="0%"   stopColor="#ffe868" />
          <stop offset="42%"  stopColor="#e09020" />
          <stop offset="100%" stopColor="#7a3808" />
        </radialGradient>

        {/* Cream muzzle */}
        <radialGradient id="ccMuzzle" cx="50%" cy="42%" r="58%">
          <stop offset="0%"   stopColor="#fff8e4" />
          <stop offset="100%" stopColor="#f5dcaa" />
        </radialGradient>

        {/* Subtle hex grid — digital fur texture */}
        <pattern id="ccHex" x="0" y="0" width="18" height="15.6" patternUnits="userSpaceOnUse">
          <polygon
            points="9,0 18,4.5 18,13.5 9,18 0,13.5 0,4.5"
            fill="none" stroke="rgba(0,0,0,0.07)" strokeWidth="0.55"
          />
        </pattern>

        {/* CRT scanlines on the iris */}
        <pattern id="ccScan" x="0" y="0" width="3" height="6" patternUnits="userSpaceOnUse">
          <rect width="3" height="5" fill="transparent" />
          <rect y="5" width="3" height="1" fill="rgba(0,0,0,0.10)" />
        </pattern>

        {/* Clip to head shape for hex overlay */}
        <clipPath id="ccHeadClip">
          <ellipse cx="100" cy="120" rx="76" ry="72" />
        </clipPath>

        {/* Clip to each iris for scanlines */}
        <clipPath id="ccLIris">
          <ellipse cx="70" cy="108" rx="20" ry="18" />
        </clipPath>
        <clipPath id="ccRIris">
          <ellipse cx="130" cy="108" rx="20" ry="18" />
        </clipPath>

        {/* Soft cyan bloom behind eyes */}
        <filter id="ccBloom" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="4.5" />
        </filter>

        {/* Very subtle outer glow on whole mark */}
        <filter id="ccOuterGlow" x="-8%" y="-8%" width="116%" height="116%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="b" />
          <feColorMatrix in="b" type="matrix"
            values="0 0 0 0 0   0 0.83 0 0 0   0 0 1 0 0   0 0 0 0.25 0"
            result="c" />
          <feMerge><feMergeNode in="c" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* ── OUTER GLOW wrapper ── */}
      <g filter="url(#ccOuterGlow)">

        {/* ── EARS ── */}
        {/* Left ear outer */}
        <path d="M36,94 L24,26 L80,76 Z" fill="#a84e10" />
        {/* Left inner ear */}
        <path d="M40,90 L32,34 L76,75 Z" fill="#f5ac80" />
        {/* Left inner ear circuit trace */}
        <path d="M52,64 H57 V58 H63" stroke="#d07840" strokeWidth="1.3"
              strokeLinecap="round" strokeLinejoin="round" fill="none" opacity="0.65" />
        <circle cx="57" cy="64" r="1.6" fill="#d07840" opacity="0.65" />
        <circle cx="57" cy="58" r="1.6" fill="#d07840" opacity="0.65" />

        {/* Right ear outer */}
        <path d="M164,94 L176,26 L120,76 Z" fill="#a84e10" />
        {/* Right inner ear */}
        <path d="M160,90 L168,34 L124,75 Z" fill="#f5ac80" />
        {/* Right inner ear circuit trace */}
        <path d="M148,64 H143 V58 H137" stroke="#d07840" strokeWidth="1.3"
              strokeLinecap="round" strokeLinejoin="round" fill="none" opacity="0.65" />
        <circle cx="143" cy="64" r="1.6" fill="#d07840" opacity="0.65" />
        <circle cx="143" cy="58" r="1.6" fill="#d07840" opacity="0.65" />

        {/* ── HEAD ── big, round, chubby */}
        <ellipse cx="100" cy="120" rx="76" ry="72" fill="url(#ccFur)" />
        {/* Hex texture overlay */}
        <rect x="0" y="0" width="200" height="200" fill="url(#ccHex)" clipPath="url(#ccHeadClip)" />

        {/* ── CHEEK BLUSH ── soft pink ovals */}
        <ellipse cx="40" cy="130" rx="18" ry="11" fill="#ff8888" opacity="0.20" />
        <ellipse cx="160" cy="130" rx="18" ry="11" fill="#ff8888" opacity="0.20" />

        {/* ── MUZZLE ── plump cream area */}
        <ellipse cx="100" cy="140" rx="40" ry="27" fill="url(#ccMuzzle)" />

        {/* ── CIRCUIT TABBY STRIPES (PCB trace style) ── */}
        {/* Stripe 1 — topmost arch */}
        <path d="M73,80 H82 V75 H118 V80"
              stroke="#944010" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="82" cy="80" r="2.3" fill="#944010" />
        <circle cx="82" cy="75" r="2.3" fill="#944010" />
        <circle cx="118" cy="75" r="2.3" fill="#944010" />
        <circle cx="118" cy="80" r="2.3" fill="#944010" />

        {/* Stripe 2 */}
        <path d="M68,90 H78 V85 H122 V90"
              stroke="#944010" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="78" cy="90" r="2.0" fill="#944010" />
        <circle cx="78" cy="85" r="2.0" fill="#944010" />
        <circle cx="122" cy="85" r="2.0" fill="#944010" />
        <circle cx="122" cy="90" r="2.0" fill="#944010" />

        {/* Stripe 3 */}
        <path d="M70,99 H79 V95 H121 V99"
              stroke="#944010" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="79" cy="99" r="1.8" fill="#944010" />
        <circle cx="79" cy="95" r="1.8" fill="#944010" />
        <circle cx="121" cy="95" r="1.8" fill="#944010" />
        <circle cx="121" cy="99" r="1.8" fill="#944010" />

        {/* ── LEFT EYE ── */}
        {/* Cyan bloom */}
        <ellipse cx="70" cy="108" rx="28" ry="26" fill="#00d4ff" opacity="0.22" filter="url(#ccBloom)" />
        {/* Eye socket */}
        <ellipse cx="70" cy="108" rx="24" ry="22" fill="#0e0804" />
        {/* Amber iris */}
        <ellipse cx="70" cy="108" rx="20" ry="18" fill="url(#ccIris)" />
        {/* Scanline overlay on iris */}
        <ellipse cx="70" cy="108" rx="20" ry="18" fill="url(#ccScan)" clipPath="url(#ccLIris)" />
        {/* Vertical slit pupil */}
        <ellipse cx="70" cy="108" rx="5.5" ry="14" fill="#050200" />
        {/* Digital horizontal sight line */}
        <line x1="65" y1="108" x2="75" y2="108" stroke="#00d4ff" strokeWidth="0.9" opacity="0.55" />
        {/* Primary specular highlight */}
        <ellipse cx="76" cy="100" rx="4.5" ry="3.5" fill="white" opacity="0.85" />
        {/* Small secondary glint */}
        <circle cx="63" cy="116" r="2.0" fill="white" opacity="0.30" />
        {/* Cyan ring */}
        <ellipse cx="70" cy="108" rx="24" ry="22" stroke="#00d4ff" strokeWidth="1.5" fill="none" opacity="1" />

        {/* Left eye HUD targeting brackets */}
        <path d="M41,86 V79 H48"  stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />
        <path d="M92,79 H99 V86"  stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />
        <path d="M41,130 V137 H48" stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />
        <path d="M92,137 H99 V130" stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />

        {/* ── RIGHT EYE ── */}
        <ellipse cx="130" cy="108" rx="28" ry="26" fill="#00d4ff" opacity="0.22" filter="url(#ccBloom)" />
        <ellipse cx="130" cy="108" rx="24" ry="22" fill="#0e0804" />
        <ellipse cx="130" cy="108" rx="20" ry="18" fill="url(#ccIris)" />
        <ellipse cx="130" cy="108" rx="20" ry="18" fill="url(#ccScan)" clipPath="url(#ccRIris)" />
        <ellipse cx="130" cy="108" rx="5.5" ry="14" fill="#050200" />
        <line x1="125" y1="108" x2="135" y2="108" stroke="#00d4ff" strokeWidth="0.9" opacity="0.55" />
        <ellipse cx="136" cy="100" rx="4.5" ry="3.5" fill="white" opacity="0.85" />
        <circle cx="123" cy="116" r="2.0" fill="white" opacity="0.30" />
        <ellipse cx="130" cy="108" rx="24" ry="22" stroke="#00d4ff" strokeWidth="1.5" fill="none" opacity="1" />

        {/* Right eye HUD targeting brackets */}
        <path d="M101,86 V79 H108"  stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />
        <path d="M152,79 H159 V86"  stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />
        <path d="M101,130 V137 H108" stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />
        <path d="M152,137 H159 V130" stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.90" />

        {/* ── NOSE ── small vivid diamond */}
        <path d="M93,130 L100,122 L107,130 L100,138 Z" fill="#ff6e88" />

        {/* Philtrum */}
        <line x1="100" y1="138" x2="100" y2="146"
              stroke="#e05070" strokeWidth="1.8" strokeLinecap="round" />

        {/* Happy smile */}
        <path d="M86,146 Q100,158 114,146"
              stroke="#e05070" strokeWidth="1.8" strokeLinecap="round" fill="none" />

        {/* ── WHISKER DOTS ── */}
        <circle cx="62" cy="134" r="2.0" fill="#884018" opacity="0.65" />
        <circle cx="60" cy="142" r="2.0" fill="#884018" opacity="0.65" />
        <circle cx="138" cy="134" r="2.0" fill="#884018" opacity="0.65" />
        <circle cx="140" cy="142" r="2.0" fill="#884018" opacity="0.65" />

        {/* ── WHISKERS ── */}
        <line x1="60"  y1="134" x2="10"  y2="126" stroke="#eedd9a" strokeWidth="0.9" opacity="0.60" />
        <line x1="60"  y1="140" x2="10"  y2="142" stroke="#eedd9a" strokeWidth="0.9" opacity="0.60" />
        <line x1="60"  y1="146" x2="12"  y2="158" stroke="#eedd9a" strokeWidth="0.9" opacity="0.55" />

        <line x1="140" y1="134" x2="190" y2="126" stroke="#eedd9a" strokeWidth="0.9" opacity="0.60" />
        <line x1="140" y1="140" x2="190" y2="142" stroke="#eedd9a" strokeWidth="0.9" opacity="0.60" />
        <line x1="140" y1="146" x2="188" y2="158" stroke="#eedd9a" strokeWidth="0.9" opacity="0.55" />

      </g>
    </svg>
  )
}
