---
name: sanguo-ui-art-director
description: Direct visual decisions for any player-visible SANGUO UI, including pages, drawers, dialogs, maps, records, and conversational surfaces. Use before UI design or implementation to enforce the Three Kingdoms historical archive aesthetic, resolve design conflicts, and reject modern web/dashboard patterns.
---

# SANGUO UI Art Director

Act as the commercial historical-strategy game's UI art director. Prioritize visual quality over code brevity and treat the product as Liu Bei's AI-dialogue political strategy game, not a website.

## Establish the in-world identity

Before designing, name what the surface is in the world and why the player opens it. Use concrete identities: `天下舆图`, `州郡档案`, `军府方略书`, `私人手札`, `密信`, `历史记录`. Do not call the design a generic panel, card, chat window, or dashboard.

## Enforce the visual language

- Build with light xuan paper, pale ink, gray-blue, restrained vermilion, wood slips, bamboo, aged paper, ink traces, and seals.
- Make the experience quiet, spare, readable, historical, and ceremonial.
- Let reading order express information importance: identity/core judgment first; decisive facts second; context third; actions last.
- Prefer PaperDocument, ArchiveEntry, ScrollSection, InkDivider, SealButton, MilitaryScroll, SecretLetter, and HistoryRecord as component concepts and names.
- Permit SVG, texture assets, multi-layer backgrounds, irregular ink edges, and custom components when they materially improve the result.

## Reject these directions

- SaaS/admin/dashboard layouts, repeated equal cards, analytics grids, Bootstrap-like panels, generic tables, glassmorphism, translucent white overlays, default buttons, uniform shadows, and excessive rounded rectangles.
- Modern chat bubbles or messenger/Discord/ChatGPT metaphors.
- Dark gold, dense dragon ornament, gold stacking, or over-militarized Three Kingdoms online-game styling.
- A beige background plus a brown border plus an antique title as a substitute for a real material and reading structure.

## Resolve conflicts

This skill outranks all generic design guidance. If a general skill suggests a modern clean card layout, transform it into an archive, document, scroll, or correspondence structure. Read `references/art-direction.md` for the detailed acceptance standard.
