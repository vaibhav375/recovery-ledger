# Recovery Ledger — dashboard front end

React + TypeScript + Vite, built on **[ThreeUI](https://github.com/MengTo/threeui)**
by Meng To (MIT).

## What is used from ThreeUI

| From ThreeUI | Where |
|---|---|
| `src/styles.css` — the full design-token stylesheet | `src/vendor/threeui-styles.css` |
| `src/theme.ts` — light/dark/system modes and the five palettes | `src/vendor/theme.ts` |
| App shell structure (`topbar`, `app`, `sidebar`, `pane`, `pane-scroll`) | `src/App.tsx` |
| Browse-grid and filter classes (`browse-page`, `browse-header`, `browse-grid`, `browse-filter`, `browse-category-filters`, `card`, `lede`, `icon-btn`) | throughout `src/components/` |

Every colour, radius and font in `src/app.css` is a ThreeUI custom property —
nothing is hard-coded — so all five palettes (mono, sepia, azure, moss, mauve)
and all three theme modes work unmodified. The licence is preserved at
`src/vendor/THREEUI-LICENSE`.

ThreeUI's Three.js/WebGL shader components are not used: this is a compliance
audit tool and there is nothing here to render in 3D.

## Design system and motion

| Source | Used for |
|---|---|
| **[ThreeUI](https://github.com/MengTo/threeui)** (MIT) | `styles.css` design tokens, `theme.ts` (light/dark/system + 5 palettes), the app shell (`topbar`/`app`/`sidebar`/`pane`), browse-grid + filter classes, and the `DotMatrixBackground` WebGL shader template in the hero |
| **[Realtime Colors](https://www.realtimecolors.com/?colors=050315-fbfbfe-2f27ce-dedcff-433bff&fonts=Inter-Inter)** | The palette — text `#050315`, background `#fbfbfe`, primary `#2f27ce`, secondary `#dedcff`, accent `#433bff` — and Inter. Applied in `src/theme.css` by re-pointing ThreeUI's own tokens, so every ThreeUI class keeps working |
| **[Motion Primitives](https://motion-primitives.com/)** patterns, on [Motion](https://motion.dev) | `AnimatedNumber` (spring counters on the hero figures), `TextEffect` (per-word blur-and-rise), `InView` (staggered reveals), `AnimatedTabs` (shared-`layoutId` nav pill) |
| **[Lenis](https://lenis.dev/)** | Smooth scrolling, disabled under `prefers-reduced-motion` |

`three` is lazily imported so its ~500KB chunk never blocks first paint, and is
skipped entirely for reduced-motion users.

## Running

```bash
npm install
npm run dev          # vite dev server, expects ../dashboard/dist/data.json
npm run build        # compiles to ../dashboard/dist
```

From the repository root:

```bash
make dashboard        # builds the front end and regenerates data.json
make dashboard-serve  # serves it at http://localhost:5174
make frontend-dev     # vite dev server with hot reload
```

`data.json` is produced by `dashboard/build_dashboard.py` from the hash-chained
ledger, so the front end always reflects the most recent `make eval`.

**It needs a server, not a double-click** — the app fetches `data.json`, and
browsers block `fetch` over `file://`. For an environment with no Node, the
Python builder also emits `dashboard/index.html`, a dependency-free single-file
version that does open directly.
