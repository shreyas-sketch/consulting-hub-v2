/** @type {import('tailwindcss').Config} */
// Consultation Hub tokens live in src/index.css (--bz-* vars, "the chamber": bottle green, brass, ivory, ink-blue).
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        bz: ['"Manrope Variable"', "Manrope", "Inter", "system-ui", "sans-serif"],
        display: ['"Newsreader Variable"', "Newsreader", "Georgia", "serif"],
        bzmono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        bzsheet: "0 -12px 48px rgba(2,10,8,0.6)",
        bzframe: "var(--card-shadow)",
        float: "0 40px 90px rgba(2,10,8,0.65)",
        goldglow: "0 10px 24px -12px rgba(212,176,106,0.55)",
        tealglow: "none",
      },
      borderRadius: {
        // Radius follows role, not one value everywhere: frames 12, sheets 8, controls 6, tags 4.
        bzframe: "12px",
        bzcard: "8px",
        bzbtn: "6px",
        bztag: "4px",
      },
      letterSpacing: {
        kicker: "0.18em",
        wordmark: "0.26em",
      },
      colors: {
        bz: {
          bg: "rgb(var(--bz-bg-rgb) / <alpha-value>)",
          spine: "rgb(var(--bz-spine-rgb) / <alpha-value>)",
          panel: "rgb(var(--bz-panel-rgb) / <alpha-value>)",
          card: "rgb(var(--bz-card-rgb) / <alpha-value>)",
          raised: "rgb(var(--bz-raised-rgb) / <alpha-value>)",
          ink: "rgb(var(--bz-ink-rgb) / <alpha-value>)",
          muted: "var(--bz-muted)",
          faint: "var(--bz-faint)",
          line: "rgb(var(--bz-line-rgb) / <alpha-value>)",
          "line-strong": "rgb(var(--bz-line-strong-rgb) / <alpha-value>)",
          inset: "var(--bz-inset)",
          accent: "var(--bz-accent)",
          "accent-deep": "var(--bz-accent-deep)",
          "accent-tint": "var(--bz-accent-tint)",
          "on-accent": "rgb(var(--bz-on-accent-rgb) / <alpha-value>)",
          miss: "rgb(var(--bz-miss-rgb) / <alpha-value>)",
          "miss-tint": "var(--bz-miss-tint)",
          gold: "rgb(var(--bz-gold-rgb) / <alpha-value>)",
          "gold-light": "rgb(var(--bz-gold-light-rgb) / <alpha-value>)",
          "gold-deep": "var(--bz-gold-deep)",
          "gold-tint": "var(--bz-gold-tint)",
          rule: "rgb(var(--bz-rule-rgb) / <alpha-value>)",
          teal: "rgb(var(--bz-teal-rgb) / <alpha-value>)",
          "teal-ink": "rgb(var(--bz-teal-ink-rgb) / <alpha-value>)",
          "teal-tint": "var(--bz-teal-tint)",
          scrim: "var(--bz-scrim)",
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
