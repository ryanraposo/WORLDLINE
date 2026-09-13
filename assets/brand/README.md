# WORLDLINE brand assets

This directory is the source of truth for WORLDLINE's visual identity.

## Canonical mark

`vector/worldline-mark.svg` is the canonical WORLDLINE mark.

The favicon-derived construction is the official geometry at every scale: a dark rounded square carrying the white world/crosshair glyph, grounded center, and offset observation node. Favicons, application icons, lockups, documentation art, social cards, and motion states all derive from this exact construction.

### Geometry invariant

The canonical geometry is intentionally shared from 16 px through display scale. `worldline-favicon.svg` and `worldline-mark-compact.svg` are aliases for integration contexts, not alternate logos.

The mark's visual semantics are:

- **Circle** — world state.
- **Crosshair** — addressability and precise agency within that world.
- **Center** — the grounded current state.
- **Offset node** — changing evidence / active observation.
- **Orbit in motion variants** — WORLDLINE continuously relating new evidence to a persistent world model.

## Files

- `vector/worldline-mark.svg` — canonical mark.
- `vector/worldline-mark-reverse.svg` — light-field inverse.
- `vector/worldline-favicon.svg` — canonical geometry under the conventional web filename.
- `vector/worldline-mark-compact.svg` — canonical geometry alias for dense UI.
- `vector/worldline-icon.svg` / `worldline-icon-light.svg` — application icon editions.
- `vector/worldline-lockup.svg` / `worldline-lockup-reverse.svg` — horizontal identity lockups.
- `vector/worldline-readme-header.svg` — repository/documentation header.
- `vector/worldline-social-card.svg` — social / Open Graph card.
- `vector/worldline-mark-motion.svg` — canonical mark with the observation node in orbit.
- `vector/worldline-loader.svg` — animated loading state.
- `raster/` — production PNG exports.
- `favicon.ico` — 16/32/64 px multi-size favicon.
- `manifest.json` — asset metadata and canonical designation.

## Usage rule

When a new WORLDLINE surface needs branding, derive it from `vector/worldline-mark.svg`. Preserve the circle, crosshair, center, observation-node relationship, proportions, and rounded-square field. Adapt scale, surrounding composition, and motion to the surface while keeping the mark itself canonical.
