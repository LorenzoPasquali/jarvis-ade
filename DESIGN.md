---
version: alpha
name: "Jarvis"
description: "A quiet local workbench for tracking projects and keeping agent conversations in their proper lanes."
colors:
  canvas: "#141A18"
  sidebar: "#171F1C"
  surface: "#1B2421"
  raised: "#222D29"
  hover: "#293631"
  border: "#35423C"
  primary: "#8CD7B2"
  accent: "#E4AA70"
  text: "#EAF0EC"
  muted: "#A2B0AA"
  danger: "#DB7D75"
  success: "#8CC89E"
  focus: "#C4F3DE"
typography:
  sans:
    fontFamily: "Segoe UI, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
rounded:
  sm: "0.45rem"
  md: "0.75rem"
  lg: "1rem"
spacing:
  unit: "0.25rem"
  sidebar-width: "15rem"
  content-max: "76rem"
components:
  button:
    radius: "0.65rem"
    min-height: "2.75rem"
  card:
    radius: "1rem"
    border: "1px solid colors.border"
    elevation: "none"
  navigation-item:
    radius: "0.65rem"
---

# Jarvis Design System

## Overview

### Creative North Star

Jarvis should feel like a well-kept developer's workbench: quiet enough for long sessions, precise enough to keep several project threads apart. The UI borrows its order from a desk of labeled project folders and instrument readouts, not from a science-fiction HUD.

### Product context and register

- **Audience and primary job:** One developer moving between local projects and independent Claude Code sessions; open the app directly into one central conversation, orient quickly, and choose the right thread.
- **Target market(s) and evidence:** Personal desktop tool for the user; no public-market assumptions.
- **Locale(s) and language policy:** Brazilian Portuguese (`pt-BR`) for owned UI copy. Local dates and times use `America/Sao_Paulo`; technical identifiers remain unchanged.
- **Usage scene:** Desktop first, often left open beside editors and terminals. Preserve the shell at compact widths; do not assume a mobile workflow.
- **Register:** Product UI. Task clarity and reliable state labels lead.
- **Memorable signature:** A slim mint focus spine with a small amber marker distinguishes the selected project or pending action.
- **Restraint:** No fake project activity, counts, or connected-agent status. Empty states explain what the user can do next.
- **Anti-references:** No glowing neon grids, animated dashboards, generic AI gradients, or decorative robot imagery; they obscure project state and overstate capabilities.
- **Token ownership/runtime mapping:** CSS custom properties in `src/app/App.css` are canonical for runtime values. This file records their intent and exact values. Update both together; no generated theme artifact is used.

## Colors

The canvas is a green-leaning graphite (`canvas`) rather than pure black. Layered surfaces (`surface`, `raised`, `hover`) distinguish navigation and content without shadows. Mint (`primary`) marks the selected route and local actions; amber (`accent`) identifies an action needing attention. Text and muted text remain separate from semantic success and danger colors. The focus ring uses `focus` and must not rely on color alone for state.

## Typography

Use the platform sans stack for headings and body copy so the app works offline without fetching fonts. Use the platform monospace stack for version numbers, paths, and agent identifiers. Body copy is sentence case, with comfortable line height; avoid all-caps except short technical eyebrows.

## Layout

Use a stable 15rem navigation rail and a fluid content region capped at 76rem. The initial route is the central conversation; project catalog and settings stay one selection away. The header and route content remain separate so route changes do not shift navigation. At narrower widths the rail may collapse to icon-plus-tooltip navigation only when accessible labels remain available; content must reflow without horizontal scrolling.

## Elevation & Depth

Use tonal layers and hairline borders for hierarchy. Static content has no shadow. Reserve a small elevation for transient dialogs only. Avoid blur and glass effects that reduce text contrast.

## Shapes

Use rounded rectangles with restrained radii: 0.45rem for compact controls, 0.75rem for standard controls, and 1rem for main panels. Keep navigation and button geometry consistent. Avoid pills except for compact status labels.

## Components

### Foundational visual states

Controls use visible hover, pressed, disabled, and focus-visible states. Focus is a 2px outline using `focus` with an offset. Busy actions retain their dimensions. Reduced-motion preferences remove nonessential movement.

### Buttons and actions

Primary mint buttons are reserved for the next safe action. Neutral actions are quiet outlines or text buttons. Destructive actions use the danger role and remain separated from primary actions until their confirmation step.

### Navigation and data display

The selected route uses the mint focus spine. Agent and project identity stays visible beside any event. Status uses a label and a color marker together. Empty and unavailable states are explicit and never simulated with sample data.

### Forms and overlays

Use labeled native inputs where forms are added. Destructive confirmation is app-owned, keyboard accessible, and cancel-first. Keep error text next to the action that can recover from it.

### Iconography

Use small inline stroke icons with consistent 1.8px strokes. Icons supplement text; no essential action is icon-only without an accessible name.

### Motion

Motion confirms navigation or state change only. Use short opacity/position transitions; honor `prefers-reduced-motion` by removing them.

### Content and data visualization

Use direct Brazilian Portuguese. Prefer “projeto”, “sessão”, “caixa de entrada” and “configurações”. Never call a session active or waiting without evidence from an adapter.

## Do's and Don'ts

- **Do:** keep project identity and session destination visible wherever a reply may be routed.
- **Do:** explain when Orca or voice integration is not connected yet.
- **Do:** keep response playback hidden until the local voice engine is validated against the reference sample.
- **Don't:** invent sample projects, agent replies, unread counts, or system activity.
- **Don't:** add generic sci-fi ornament that competes with terminal and project information.
