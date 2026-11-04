/** @type {import('tailwindcss').Config} */
// Consultation Hub tokens live in src/index.css (--bz-* vars, Akshat Dani design system, dark only).
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        bz: ['"Manrope Variable"', "Manrope", "Inter", "system-ui", "sans-serif"],
        bzmono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        bzsheet: "0 -8px 40px rgba(0,0,0,0.5)",
        bzframe: "var(--card-shadow)",
        float: "0 40px 90px rgba(0,0,0,0.6)",
        goldglow: "0 0 40px rgba(201,168,76,0.25)",
        tealglow: "0 0 60px rgba(46,211,183,0.10)",
      },
      borderRadius: {
        bzcard: "14px",
        bzframe: "18px",
        bzbtn: "12px",
      },
      letterSpacing: {
        kicker: "0.18em",
        wordmark: "0.26em",
      },
      colors: {
        bz: {
          bg: "var(--bz-bg)",
          panel: "var(--bz-panel)",
          card: "var(--bz-card)",
          raised: "var(--bz-raised)",
          ink: "var(--bz-ink)",
          muted: "var(--bz-muted)",
          faint: "var(--bz-faint)",
          line: "var(--bz-line)",
          "line-strong": "var(--bz-line-strong)",
          inset: "var(--bz-inset)",
          accent: "var(--bz-accent)",
          "accent-deep": "var(--bz-accent-deep)",
          "accent-tint": "var(--bz-accent-tint)",
          "on-accent": "var(--bz-on-accent)",
          miss: "var(--bz-miss)",
          "miss-tint": "var(--bz-miss-tint)",
          gold: "var(--bz-gold)",
          "gold-light": "var(--bz-gold-light)",
          "gold-deep": "var(--bz-gold-deep)",
          "gold-tint": "var(--bz-gold-tint)",
          rule: "var(--bz-rule)",
          teal: "var(--bz-teal)",
          "teal-ink": "var(--bz-teal-ink)",
          "teal-tint": "var(--bz-teal-tint)",
          scrim: "var(--bz-scrim)",
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
