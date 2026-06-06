# Fonts

**This folder is intentionally empty.**

The production Tomorrowland codebase does not ship a webfont — it relies on
the **system Inter stack** with a generous fallback to UI-sans / Segoe / etc.
This design system substitutes Inter loaded from Google Fonts at the top of
`../colors_and_type.css` so that designs render consistently across machines
without Inter installed.

**If you have a brand-licensed Inter Variable woff2 (or a successor face),
drop it here as e.g. `Inter-Variable.woff2`** and replace the `@import` at
the top of `colors_and_type.css` with an `@font-face` rule pointing at it:

```css
@font-face {
  font-family: "Inter";
  src: url("./fonts/Inter-Variable.woff2") format("woff2-variations");
  font-weight: 100 900;
  font-display: swap;
}
```

For mono code blocks, the system already substitutes JetBrains Mono from
Google Fonts via the same `@import`. Same substitution rule applies — drop
a real file in here when you have one.
