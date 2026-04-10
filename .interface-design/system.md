# DarkFactory — Design System

## Direction

**Metaphor:** Industrial control panel. Factory floor at night with pools of light on the work.

**Feel:** Precise, industrial, lived-in. Like reading a well-maintained engineering notebook. Terminal output is the native language, not decoration. The kind of documentation where you can feel the author uses the tool daily.

**Who:** Developer at their desk, terminal split-screened with browser. Technical, skeptical of fluff. Three modes: evaluate, learn, reference.

**Signature:** The *production run*. `prd run` is literally a production run through a factory. Status indicators, sequential steps, pass/fail gates. Not abstract software diagrams — factory dispatch.

---

## Palette

### Dark Theme (primary)

| Token | Value | Role |
|-------|-------|------|
| `--sl-color-black` | `#08080a` | Void — deepest background |
| `--sl-color-gray-6` | `#0e0e10` | Factory floor — base canvas |
| `--sl-color-gray-5` | `#16161a` | Elevated — cards, sidebar |
| `--sl-color-gray-4` | `#22222a` | Border standard |
| `--sl-color-gray-3` | `#3a3a44` | Border emphasis |
| `--sl-color-gray-2` | `#8a8680` | Text tertiary — metadata |
| `--sl-color-gray-1` | `#b8b4ae` | Text secondary — supporting |
| `--sl-color-white` | `#e8e4de` | Text primary — chalk on concrete |

### Accent: Industrial Amber

| Token | Value | Role |
|-------|-------|------|
| `--sl-color-accent-low` | `#1c1608` | Amber tint backgrounds |
| `--sl-color-accent` | `#d4940a` | Primary accent — caution lights |
| `--sl-color-accent-high` | `#f0d080` | Accent text on dark surfaces |

### Borders

All borders use rgba for transparency blending — never solid hex.

| Level | Value | Usage |
|-------|-------|-------|
| Whisper | `rgba(232, 228, 222, 0.04)` | Section separation in content |
| Standard | `rgba(232, 228, 222, 0.08)` | Card edges, sidebar, nav |
| Emphasis | `rgba(232, 228, 222, 0.12)` | Focus, active states |

### Status Colors (factory LEDs)

| Status | Color | Usage |
|--------|-------|-------|
| Done | `#4a9` | Completed indicators |
| Running | `#d4940a` | Active/in-progress (amber accent) |
| Pending | `#8a8680` | Waiting (text-tertiary) |
| Blocked | `#c44` | Failed/blocked indicators |

---

## Depth Strategy

**Borders only. No shadows. Factories are precise, not soft.**

All `box-shadow` values killed globally. Structure defined by:
- 1px borders at low rgba opacity
- Surface color shifts (higher elevation = slightly lighter/warmer)
- Inset appearance for inputs and code (slightly darker than surroundings)

Sidebar uses same background as canvas — separated by border, not color.

---

## Typography

| Role | Font | Size | Weight | Tracking |
|------|------|------|--------|----------|
| Body prose | System sans-serif (Starlight default) | 1rem | 400 | Normal |
| Code (dominant voice) | JetBrains Mono, Fira Code, Cascadia Code | 0.875em | 400 | Normal |
| Headings | System sans-serif | h1: 4xl, h2: 2xl | 700 | -0.02em to -0.005em |
| Feature card titles | JetBrains Mono | 0.8125rem | 600 | 0.06em, uppercase |
| Table headers | JetBrains Mono | 0.8125rem | 600 | 0.02em, uppercase |
| Tab labels | JetBrains Mono | 0.8125rem | — | 0.02em |
| Sidebar links | System sans-serif | 0.875rem | — | 0.01em |

Terminal/monospace is the dominant voice — this is a CLI tool. Sans-serif supports, mono leads.

---

## Spacing

**Base unit:** 4px

| Scale | Value | Usage |
|-------|-------|-------|
| Micro | 4px | Icon gaps, inline code padding |
| Small | 8px | Internal card spacing |
| Component | 12-16px | Card padding (1.25rem), button padding |
| Section | 20-24px | Between content groups |
| Major | 40px (2.5rem) | Between major page sections, h2 margin-top |

---

## Border Radius

**Sharp. 4px everywhere.** No friendly rounding. Factories have edges.

- Cards: 4px
- Code blocks: 4px
- Callout boxes: 4px
- Aside components: 0 4px 4px 0 (left-border accent)
- Inline code: 3px
- Feature grid container: 4px

---

## Component Patterns

### Feature Grid (landing page)
Cards share borders via `gap: 1px` with `outline: 1px solid` on each card. Container has a single outer border. Cards don't float — they tile like instrument panels.

Title: amber, monospace, uppercase, 0.8125rem.
Body: gray-1, 0.9rem, 1.55 line-height.

### Callout Box (placard)
Amber-tinted background (`accent-low`). Border at 25% amber opacity. No radius beyond 4px. Text in `accent-high`. Bold label in `accent`.

### Section Dividers
Single 1px rule using `hairline` token. 2.5rem margin block.

### Content Headings (h2)
Bottom border in `hairline-light`. Negative letter-spacing. 2.5rem top margin. Creates section separation without extra whitespace.

### Tables (spec sheet)
Monospace uppercase headers in `gray-2`. 0.875rem body text. Top-aligned cells. Dense, scannable.

### Links
Amber colored. Underline at 30% amber opacity, full opacity on hover. 0.15em underline offset.

### Inline Code
Inset appearance: slightly darker background (6% white overlay), matching border, 3px radius. Monospace at 0.875em.

---

## Rejected Defaults

| Default | Replacement | Reason |
|---------|-------------|--------|
| Blue accent | Amber `#d4940a` | Factory caution lights, not SaaS |
| Box shadows for depth | Borders only | Factories don't float |
| Rounded corners (8-12px) | Sharp 4px | Industrial edges |
| Different sidebar color | Same as canvas + border | No "sidebar world" vs "content world" |
| Marketing hero copy | Terse factual statements | Developer audience, not buyers |
| Floating card grid | Shared-border instrument panel | Equipment panels, not sticky notes |
