---
version: alpha
name: Open Notebook — Soft Fern
description: Calm, layered, modern. A warm-neutral workspace where green acts, teal is the AI voice, and depth comes from soft elevation rather than lines.
colors:
  primary: "#2F7A57"
  primary-hover: "#276849"
  on-primary: "#F2FAF5"
  secondary: "#0F7C71"
  tertiary: "#B8862B"
  neutral: "#F7F6F2"
  surface: "#FFFFFF"
  surface-raised: "#FFFFFF"
  surface-recessed: "#F1F0EB"
  surface-sunken: "#E9E8E2"
  ink: "#1F2125"
  ink-soft: "#5A5E66"
  ink-faint: "#8B8F97"
  line: "#E6E5DF"
  line-soft: "#EEEDE7"
  danger: "#C24A34"
  danger-tint: "#FBEAE5"
  warn: "#B75A2A"
  focus: "#3FB3A5"
  dark-bg: "#141619"
  dark-bg-deep: "#0F1113"
  dark-surface: "#1C1F24"
  dark-surface-raised: "#23272D"
  dark-surface-sunken: "#2B3037"
  dark-ink: "#EEEFEA"
  dark-ink-soft: "#ADB1B8"
  dark-line: "#2F333A"
  dark-primary: "#4CA47A"
  dark-primary-hover: "#5AB489"
typography:
  display:
    fontFamily: Bricolage Grotesque
    fontSize: 2rem
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  h1:
    fontFamily: Bricolage Grotesque
    fontSize: 1.75rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  h2:
    fontFamily: Bricolage Grotesque
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body-md:
    fontFamily: Instrument Sans
    fontSize: 0.9375rem
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: Instrument Sans
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: Instrument Sans
    fontSize: 0.6875rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.08em"
  mono:
    fontFamily: Spline Sans Mono
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: 6px
  sm: 8px
  md: 10px
  lg: 14px
  xl: 18px
  pill: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 10px 16px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: 10px 16px
  button-destructive:
    backgroundColor: "{colors.danger}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
    padding: 10px 16px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: 20px
  card-hover:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
  sidebar:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.ink-soft}"
    padding: 12px
  sidebar-item-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: 8px 12px
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: 8px 12px
  badge-ai:
    backgroundColor: "#DDEFEB"
    textColor: "#0B5F57"
    rounded: "{rounded.pill}"
    padding: 2px 8px
  dialog:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: 24px
---

## Overview

Open Notebook is a research workspace: long reading sessions, many small
controls, and an AI voice that must feel distinct from the user's own notes.
"Soft Fern" keeps upstream's disciplined hue rules — **fern acts, teal speaks,
red only destroys** — but trades the flat, hairline-and-4px "instrument" look
for a modern layered surface: warmer neutrals, rounder geometry, and depth from
soft elevation instead of borders. The result should read as calm and
contemporary (think Linear/Notion) while staying unmistakably green.

## Colors

- **Primary (#2F7A57)** — fern. Every affirmative action: New, Save, Generate,
  Learn. Hover darkens to `primary-hover`. Never used as a page wash.
- **Secondary (#0F7C71)** — teal, the AI/system voice: insights, AI notes,
  citations, focus rings. Keeps human and machine content visually separate.
- **Tertiary (#B8862B)** — gold for notes, PDFs and "insights-only" context
  states. Warm counterweight to the greens.
- **Neutral surfaces** step from `neutral` (page) → `surface` (cards, inputs)
  → `surface-raised` (popovers, dialogs). Light mode is a warm off-white so
  white cards visibly lift; dark mode uses cool charcoals with the same three
  steps so hierarchy survives without borders.
- **Ink** three levels only: `ink` for content, `ink-soft` for secondary
  text, `ink-faint` for placeholders and timestamps.
- **Danger (#C24A34)** appears only on destructive buttons, error text and the
  "Quit" control. **Warn** is clay, never red, never green.

## Typography

Bricolage Grotesque for display and headings (tight tracking, 600 weight —
it gives the app a face). Instrument Sans at 15px/1.55 for body: slightly
larger than upstream's 14px to ease long reading. Spline Sans Mono only for
data (ids, counts, code), never prose. Section labels ("COLLECT", "PROCESS")
are 11px/600 with 0.08em tracking.

## Layout

12px base rhythm. Sidebar 260px with 12px inner padding and 4px gaps between
items. Cards have 20px padding and a 16px gap in grids. Dialogs cap at 640px
(forms) or 1100px (Learn classroom) and sit 24px inside the viewport.

## Elevation & Depth

Borders become optional; elevation carries hierarchy:

- `shadow-soft` (0 1px 2px @6%) — cards at rest, inputs.
- `shadow-lift` (0 2px 6px @8%, 0 12px 28px @8%) — hovered cards, dropdowns.
- `shadow-pop` (0 4px 12px @10%, 0 24px 48px @14%) — dialogs, command palette.
- Cards keep a 1px `line-soft` border in light mode for crispness on the warm
  page; dark mode drops to a 1px `dark-line` at 60% opacity.
- Hover on interactive cards: translateY(-1px) + `shadow-lift`, 150ms.

## Shapes

Rounded, not pill-shaped. `md` (10px) for buttons and inputs, `lg` (14px)
for cards, `xl` (18px) for dialogs and the command palette. Avatars, status
dots and AI badges are pills. Nothing below 6px.

## Components

- **Buttons**: primary is fern with white text; outline sits on `surface`
  with a `line` border and gains `shadow-soft` on hover; ghost has no border
  and tints `surface-sunken` on hover. Height 36px (sm 32px).
- **Sidebar**: `neutral` background, items 36px tall, active item lifts onto
  `surface` with fern text and a 2px fern bar on the left edge.
- **Cards** (notebooks, sources, notes): `surface`, 14px radius, soft shadow,
  lift on hover. Type dots and count chips use content-type hues only.
- **Inputs**: `surface`, 8px radius, `line` border; focus = 3px teal ring at
  35% opacity, no border color change.
- **Dialogs**: `surface-raised`, 18px radius, `shadow-pop`, 24px padding,
  backdrop `ink` at 40% with 6px blur.
- **AI badge**: teal tint pill, dark-teal text.

## Do's and Don'ts

- Do let elevation, not borders, separate layers.
- Do keep fern for actions and teal for anything AI-generated.
- Don't wash reading surfaces with color — tints are for chips and badges.
- Don't use red for warnings; clay is the warning hue.
- Don't shrink radii below 6px or mix pill buttons with rounded ones.
