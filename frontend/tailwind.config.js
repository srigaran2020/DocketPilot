/** Design tokens live as CSS variables in src/index.css (light and dark); Tailwind maps names onto them. */
const v = name => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: v("bg"), surface: v("surface"), raised: v("raised"), line: v("line"), "line-2": v("line-2"),
        ink: v("ink"), "ink-2": v("ink-2"), mute: v("mute"),
        brand: { DEFAULT: v("brand"), 2: v("brand-2"), soft: v("brand-soft"), ink: v("brand-ink") },
        seal: { DEFAULT: v("seal"), soft: v("seal-soft") },
        brass: { DEFAULT: v("brass"), soft: v("brass-soft") },
        ok: { DEFAULT: v("ok"), soft: v("ok-soft") },
        warn: { DEFAULT: v("warn"), soft: v("warn-soft") },
        bad: { DEFAULT: v("bad"), soft: v("bad-soft") },
      },
      fontFamily: {
        sans: ["Inter", "IBM Plex Sans", "Segoe UI", "system-ui", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
        mark: ["Cinzel", "Georgia", "serif"],
        mono: ["JetBrains Mono", "IBM Plex Mono", "Consolas", "monospace"],
      },
      borderRadius: { xl: "14px", "2xl": "18px" },
      boxShadow: {
        card: "0 1px 0 rgb(var(--line) / 1), 0 1px 2px rgb(16 24 22 / .04), 0 8px 24px -16px rgb(16 24 22 / .18)",
        pop: "0 12px 40px -12px rgb(10 20 18 / .35), 0 2px 6px rgb(10 20 18 / .08)",
        glow: "0 0 0 4px rgb(var(--brand) / .12)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        pulseDot: { "0%,80%,100%": { opacity: ".25", transform: "scale(.85)" }, "40%": { opacity: "1", transform: "scale(1)" } },
      },
      animation: { shimmer: "shimmer 1.6s infinite", dot: "pulseDot 1.2s infinite" },
    },
  },
  plugins: [],
};
