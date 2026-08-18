---
name: sanguo-ui-implementation-workflow
description: Implement approved SANGUO player-visible UI as high-fidelity historical game interfaces. Use after the Art Director and design-analysis stages for pages, components, drawers, dialogs, and responsive UI changes; require staged implementation, screenshot review, and iteration instead of direct CSS edits.
---

# SANGUO UI Implementation Workflow

Implement the approved design as a game UI technical artist. Visual fidelity takes precedence over engineering convenience and code brevity.

## Required sequence

1. Confirm the page identity, player intent, and first/second/third reading priorities.
2. State the main visual region, information region, action region, decorative region, materials, and focal order before changing code.
3. Translate the approved plan into world-specific components. Reuse existing project conventions and useful component libraries only when their visible result can meet the Art Director rules; do not introduce a generic Card/Box/Panel abstraction.
4. Use the implementation appropriate to the design: layered DOM, SVG, images, custom CSS, irregular details, and restrained motion are permitted.
5. Build/test the relevant code, then inspect real rendered screenshots at the required viewport(s) when access allows. Iterate on observed visual problems.
6. Hand the final rendered result to `sanguo-ui-visual-critic`. A score below 8/10 means continue refinement unless the user explicitly limits scope.

## Implementation constraints

- Never begin from “requirement → CSS”. CSS implements a chosen visual direction; it does not choose it.
- Do not reduce the visual design merely to write fewer lines or use stock components.
- Preserve responsiveness, keyboard focus, motion preferences, and existing functional behavior.
- If requirements materially lack a direction, offer 2–3 in-world visual directions with trade-offs and a recommendation before implementation.

Read `references/implementation-checklist.md` for the pre-code and post-render checklist.
