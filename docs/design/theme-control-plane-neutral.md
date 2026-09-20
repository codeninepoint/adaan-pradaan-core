# Theme: Control Plane Neutral

Design system tokens for the multi-tenant marketplace control-plane UI. Use this sheet when building Figma libraries or frontend implementations.

**Tone:** Trustworthy, neutral, operational (AWS Console / Vercel / Linear — restrained). Light mode only for Phase 1 auth.

---

## Color tokens

| Token | Hex | CSS variable (suggested) | Usage |
|-------|-----|--------------------------|--------|
| `color.primary` | `#2563EB` | `--cp-primary` | Primary buttons, links, focus rings |
| `color.primary.hover` | `#1D4ED8` | `--cp-primary-hover` | Button hover |
| `color.primary.muted` | `#EFF6FF` | `--cp-primary-muted` | Subtle highlights |
| `color.background` | `#F8FAFC` | `--cp-bg` | Page background |
| `color.surface` | `#FFFFFF` | `--cp-surface` | Cards, form panels |
| `color.border` | `#E2E8F0` | `--cp-border` | Inputs, dividers |
| `color.border.focus` | `#2563EB` | `--cp-border-focus` | Focused input |
| `color.text.primary` | `#0F172A` | `--cp-text` | Headings, labels |
| `color.text.secondary` | `#64748B` | `--cp-text-muted` | Helper text, placeholders |
| `color.text.inverse` | `#FFFFFF` | `--cp-text-inverse` | Text on primary buttons |
| `color.error` | `#DC2626` | `--cp-error` | Errors, destructive emphasis |
| `color.error.bg` | `#FEF2F2` | `--cp-error-bg` | Error alert background |
| `color.success` | `#16A34A` | `--cp-success` | Success toast |
| `color.success.bg` | `#F0FDF4` | `--cp-success-bg` | Success alert background |

---

## Typography

| Token | Value | Usage |
|-------|-------|--------|
| `font.family` | Inter, system-ui, -apple-system, sans-serif | All UI |
| `font.size.xs` | 12px | Captions, legal |
| `font.size.sm` | 14px | Labels, body, inputs |
| `font.size.base` | 16px | Body large, button text |
| `font.size.lg` | 20px | Card titles |
| `font.size.xl` | 24px | Page titles (mobile) |
| `font.size.2xl` | 30px | Brand panel headline |
| `font.weight.normal` | 400 | Body |
| `font.weight.medium` | 500 | Labels, buttons |
| `font.weight.semibold` | 600 | Headings |
| `line.height.tight` | 1.25 | Headings |
| `line.height.normal` | 1.5 | Body |

---

## Spacing and layout

| Token | Value | Usage |
|-------|-------|--------|
| `space.1` | 4px | Tight gaps |
| `space.2` | 8px | Icon gaps |
| `space.3` | 12px | Inline spacing |
| `space.4` | 16px | Between form fields |
| `space.6` | 24px | Card padding |
| `space.8` | 32px | Section gaps |
| `space.12` | 48px | Brand panel padding |
| `radius.sm` | 6px | Inputs |
| `radius.md` | 8px | Cards, buttons |
| `radius.lg` | 12px | Large panels |
| `shadow.card` | `0 1px 3px rgba(15,23,42,0.08)` | Auth form card |
| `layout.form.maxWidth` | 400px | Login/register form |
| `layout.split.brand` | 40% | Desktop brand panel width |
| `layout.split.form` | 60% | Desktop form column |

---

## Component specs

### Button — Primary

- Background: `color.primary`, hover `color.primary.hover`
- Text: `color.text.inverse`, `font.size.base`, `font.weight.medium`
- Padding: 10px 16px, height 40px, `radius.md`
- Disabled: opacity 0.5, no pointer

### Button — Secondary (link style)

- Text: `color.primary`, underline on hover
- No border

### Input

- Height: 40px, padding 0 12px
- Border: 1px `color.border`, focus 2px ring `color.primary`
- Background: `color.surface`
- Label: `font.size.sm`, `font.weight.medium`, `color.text.primary`, 8px above field
- Error state: border `color.error`, helper text `color.error`

### Form card

- Background: `color.surface`, `radius.md`, `shadow.card`
- Padding: `space.6` (24px)
- Max width: `layout.form.maxWidth`

### Alert — Error

- Background: `color.error.bg`, border 1px `color.error`, text `color.error`
- Padding: 12px 16px, `radius.sm`

---

## Figma library setup (manual)

Create a Figma file **“Control Plane — Design System”** with:

1. **Color styles** — map each token above to Figma color styles (`Primary/600`, `Surface/Default`, etc.).
2. **Text styles** — `Heading/Card`, `Body/Default`, `Label/Field`, `Caption/Muted`.
3. **Components** — Button/Primary, Button/Secondary, Input/Default, Input/Error, Alert/Error, Alert/Success, Card/Form.
4. **Auth page** — duplicate components into page **“Auth — Phase 1”** per [auth-screens.md](auth-screens.md).

Export CSS variables from this doc when implementing frontend (Phase 2).

---

## Brand panel copy (auth)

- **Headline:** Run, consume, and publish integrations in one place.
- **Sub:** For individuals and organizations — marketplace, resources, and billing on a shared control-plane.
- **Product name:** Tenant Control Plane (placeholder logo: monogram “TCP” in primary blue)

---

## Accessibility

- Minimum contrast ratio 4.5:1 for body text on background (WCAG AA).
- Focus visible: 2px `color.primary` outline, offset 2px.
- Touch targets minimum 40px height.
- Associate errors with fields via `aria-describedby` in implementation.

---

## Related

- [auth-screens.md](auth-screens.md) — wireframes and flows
- [session-flow.md](session-flow.md) — token and `/v1/auth/me` behavior
