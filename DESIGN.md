---
version: alpha
name: llmux-dashboard
description: Design system for the LLMux admin dashboard — operational monitoring, cost management, and provider health
colors:
  surface-primary: "#FAFBFC"
  surface-secondary: "#FFFFFF"
  surface-tertiary: "#F0F2F5"
  text-primary: "#1A1C1E"
  text-secondary: "#586069"
  text-tertiary: "#8B949E"
  brand: "#2B7489"
  brand-hover: "#236272"
  success: "#1A7F37"
  warning: "#BF8700"
  danger: "#CF222E"
  info: "#0969DA"
  chart-1: "#2B7489"
  chart-2: "#8250DF"
  chart-3: "#BF8700"
  chart-4: "#CF222E"
  chart-5: "#1A7F37"
  border-default: "#D0D7DE"
  border-muted: "#E1E4E8"
  focus-ring: "#0969DA"
  overlay: "rgba(27, 31, 36, 0.5)"
typography:
  heading-xl:
    fontFamily: Inter
    fontSize: 1.75rem
    fontWeight: "600"
    lineHeight: 1.3
    letterSpacing: -0.02em
  heading-lg:
    fontFamily: Inter
    fontSize: 1.375rem
    fontWeight: "600"
    lineHeight: 1.3
    letterSpacing: -0.01em
  heading-md:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: "600"
    lineHeight: 1.4
    letterSpacing: 0
  body-md:
    fontFamily: Inter
    fontSize: 0.9375rem
    fontWeight: "400"
    lineHeight: 1.5
    letterSpacing: 0
  body-sm:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: "400"
    lineHeight: 1.5
    letterSpacing: 0
  code-md:
    fontFamily: "JetBrains Mono"
    fontSize: 0.8125rem
    fontWeight: "400"
    lineHeight: 1.5
    letterSpacing: 0
  label-md:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: "500"
    lineHeight: 1.4
    letterSpacing: 0.01em
    fontFeature: "calt, ss02"
rounded:
  none: 0
  sm: 4px
  md: 8px
  lg: 12px
  xl: 16px
  full: 9999px
spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  xxxl: 64px
components:
  sidebar:
    backgroundColor: "{colors.surface-secondary}"
    textColor: "{colors.text-primary}"
    rounded: none
    width: 260px
  sidebar-item:
    backgroundColor: transparent
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    padding: 8px 12px
  sidebar-item-active:
    backgroundColor: "rgba(43, 116, 137, 0.08)"
    textColor: "{colors.brand}"
    rounded: "{rounded.md}"
    padding: 8px 12px
  topbar:
    backgroundColor: "{colors.surface-secondary}"
    textColor: "{colors.text-primary}"
    rounded: none
    padding: 0 24px
    height: 56px
  card:
    backgroundColor: "{colors.surface-secondary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: 20px
  card-metric:
    backgroundColor: "{colors.surface-secondary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: 16px
  table-header:
    backgroundColor: "{colors.surface-tertiary}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.label-md}"
    rounded: none
    padding: 8px 12px
  table-cell:
    backgroundColor: transparent
    textColor: "{colors.text-primary}"
    typography: "{typography.body-sm}"
    rounded: none
    padding: 8px 12px
  badge-success:
    backgroundColor: "rgba(26, 127, 55, 0.08)"
    textColor: "{colors.success}"
    rounded: "{rounded.full}"
    padding: 2px 8px
  badge-warning:
    backgroundColor: "rgba(191, 135, 0, 0.08)"
    textColor: "{colors.warning}"
    rounded: "{rounded.full}"
    padding: 2px 8px
  badge-danger:
    backgroundColor: "rgba(207, 34, 46, 0.08)"
    textColor: "{colors.danger}"
    rounded: "{rounded.full}"
    padding: 2px 8px
  badge-info:
    backgroundColor: "rgba(9, 105, 218, 0.08)"
    textColor: "{colors.info}"
    rounded: "{rounded.full}"
    padding: 2px 8px
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
    padding: 8px 16px
    height: 36px
  button-secondary:
    backgroundColor: transparent
    textColor: "{colors.text-primary}"
    borderColor: "{colors.border-default}"
    rounded: "{rounded.md}"
    padding: 8px 16px
    height: 36px
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
    padding: 8px 16px
    height: 36px
  input:
    backgroundColor: "{colors.surface-primary}"
    textColor: "{colors.text-primary}"
    borderColor: "{colors.border-default}"
    rounded: "{rounded.md}"
    padding: 8px 12px
    height: 36px
  input-focus:
    backgroundColor: "{colors.surface-primary}"
    textColor: "{colors.text-primary}"
    borderColor: "{colors.focus-ring}"
    rounded: "{rounded.md}"
    padding: 8px 12px
    height: 36px
  select:
    backgroundColor: "{colors.surface-primary}"
    textColor: "{colors.text-primary}"
    borderColor: "{colors.border-default}"
    rounded: "{rounded.md}"
    padding: 8px 12px
    height: 36px
---

# LLMux Dashboard Design

## Overview

The LLMux dashboard is an operational interface for managing and monitoring an LLM gateway. Primary users are platform engineers who need to track provider health, usage patterns, cost attribution, and configuration. The design prioritizes **data density, scannability, and at-a-glance status awareness** — this is a monitoring tool, not a marketing site.

### Design Personality

- **Professional and precise**: clear hierarchies, structured layouts, data-forward
- **Neutral palette with teal accent**: teal (`#2B7489`) as the brand color conveys reliability and technology without being generic blue
- **Low visual noise**: generous whitespace, subtle borders, restrained use of color (reserved for semantic meaning: green = healthy, red = error, yellow = warning, blue = info)
- **Monochromatic data visualization**: a 5-color categorical palette for charts, designed to be distinguishable in both light mode and when printed in grayscale

## Colors

### Semantic Roles

| Token | Role | Usage |
|-------|------|-------|
| `brand` | Primary accent | Navigation active state, primary buttons, chart primary series, links |
| `success` | Positive state | Provider healthy, budget OK, rate limit OK |
| `warning` | Degraded state | Provider degraded, budget approaching limit, rate limit near cap |
| `danger` | Error state | Provider down, budget exceeded, rate limit exceeded, errors |
| `info` | Informational | Audit log entries, system notifications, help text |

### Surface Hierarchy

Three surface levels create depth: `surface-primary` (page background), `surface-secondary` (card/sidebar background), `surface-tertiary` (table headers, section dividers). This provides visual hierarchy without relying on shadows alone.

## Typography

### Font Stack

- **UI**: Inter (system font fallback: -apple-system, BlinkMacSystemFont, "Segoe UI")
- **Code/Monospace**: JetBrains Mono (system fallback: "SF Mono", Monaco, "Cascadia Code")

### Hierarchy

- **heading-xl** (28px/1.75rem): Page titles — used once per view
- **heading-lg** (22px/1.375rem): Section headings — primary content sections
- **heading-md** (18px/1.125rem): Card titles, sidebar section labels
- **body-md** (15px/0.9375rem): Default body text — most content
- **body-sm** (13px/0.8125rem): Secondary text, table cells, metadata
- **code-md** (13px/0.8125rem): Code blocks, inline code, metric values
- **label-md** (13px/0.8125rem, 500 weight): Table headers, form labels, badge text

## Layout

### Dashboard Structure

```text
+--+----------------------------------------+
|  | Top Bar (56px)                          |
|  | Breadcrumb | Search | User Menu         |
+--+----------------------------------------+
|  |                                        |
|S |                                        |
|i |           Main Content Area            |
|d |                                        |
|e |                                        |
|b |                                        |
|a |                                        |
|r |                                        |
+--+----------------------------------------+
```

- **Sidebar**: 260px fixed, scrollable, contains primary navigation sections
- **Top bar**: 56px, sticky, contains breadcrumb, global search, user menu
- **Main content**: flexible, 24px padding, responsive grid for metric cards
- **Layout**: CSS Grid with `grid-template-columns: 260px 1fr` on desktop; sidebar collapses to overlay drawer on < 768px

### Responsive Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| Desktop | > 1024px | Full sidebar + multi-column grids |
| Tablet | 768–1024px | Collapsed sidebar (icon-only) + 2-column grids |
| Mobile | < 768px | Overlay drawer sidebar + single column |

## Navigation

### Primary Navigation (Sidebar)

| Section | Icon | Description |
|---------|------|-------------|
| Overview | Dashboard icon | Summary metrics, health at a glance |
| Providers | Server icon | Provider list, health detail, configuration |
| Usage | Chart icon | Usage charts, trends, export |
| Cost | Dollar icon | Cost breakdown by team/provider/model |
| Rate Limits | Gauge icon | Rate limit configuration and monitoring |
| Budgets | Wallet icon | Budget configuration, current spend, alerts |
| API Keys | Key icon | API key management, scopes, usage per key |
| Audit Log | Clipboard icon | Searchable, filterable audit log |
| Settings | Gear icon | System configuration |

### Breadcrumb Pattern

`Overview > Providers > OpenAI` — each segment is clickable. Breadcrumb appears below the top bar.

## States

### Metric Cards

| State | Visual | Behavior |
|-------|--------|----------|
| Loading | Skeleton block matching card dimensions | Shimmer animation |
| Loaded | Card with metric value, label, trend indicator | — |
| Empty | Metric value shows "—" or "0" | No trend indicator |
| Error | Card with dashed border, error icon, "Failed to load" | Visible retry button |
| Degraded | Metric value with warning color | Last-known value shown with timestamp |

### Tables

| State | Visual | Behavior |
|-------|--------|----------|
| Loading | N skeleton rows | Shimmer animation |
| Loaded | Data rows with alternating backgrounds | Horizontal scroll on overflow |
| Empty | Empty state illustration + "No records found" + CTA | — |
| Error | Error state in table area | "Failed to load data" + retry |
| Refreshing | Previous data visible, subtle loading indicator at top | Auto-refresh badge shows "Updating..." |

### Providers List

| State | Visual | Behavior |
|-------|--------|----------|
| Healthy | Green badge "Active", latency shown | Expandable to see model list |
| Degraded | Yellow badge "Degraded", last healthy timestamp | Expandable with error details |
| Down | Red badge "Down", last healthy timestamp | Expandable with error details, auto-retry badge |
| Disabled | Gray badge "Disabled", muted row | Cannot be selected for routing |
| Configuring | Blue badge "Configuring" | Initial setup state, provider not yet available |

## Accessibility

- All interactive elements must be keyboard accessible (Tab, Enter, Escape, Arrow navigation)
- Focus indicators: 2px blue (`#0969DA`) ring with 2px offset on all focusable elements
- Color is never the sole indicator of state — badges use icons and text labels alongside color
- Charts: pattern fills or labels alongside color for series differentiation
- Screen reader announcements for: page navigation, data loading completion, error states, auto-refresh events
- Minimum touch target: 44×44px for all interactive elements on mobile
- Color contrast: all text/background combinations meet WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text)

## Charts & Data Visualization

### Guidelines

- All charts display loading, empty, error, and data states
- Time series default to last 7 days with 1-hour buckets
- Hover tooltips show exact value, timestamp, and any relevant secondary metric
- Legends are always visible; never rely on hover alone to identify series
- Chart colors use the 5-color categorical palette (`chart-1` through `chart-5`)
- Monochrome-friendly: series also differ by line style (solid, dashed, dotted) where feasible

### Chart Types

| Chart | Location | Type |
|-------|----------|------|
| Requests over time | Overview, Usage | Area/line chart (stacked by provider) |
| Cost over time | Cost | Area/line chart (stacked by provider) |
| Latency heatmap | Providers | Heat map by hour × provider |
| Token distribution | Usage | Stacked bar (prompt vs completion) |
| Top models by cost | Cost | Horizontal bar chart |
| Budget gauge | Budgets | Semi-circular gauge |

## Components

### Metric Card

A compact card displaying a single metric with label, current value, trend direction, and optional sparkline.

- **States**: loading (skeleton), loaded, empty (—), error (dashed border + retry)
- **Responsive**: 1 column on mobile, up to 4 columns on desktop in a metric grid
- **Accessibility**: value announced as "Value: [number], Trend: [up/down] [percentage]"

### Status Badge

Small pill indicating operational state.

- **Variants**: success, warning, danger, info, disabled
- **Content**: icon (check/exclamation/x/info) + short text label
- **States**: all variants

### Data Table

Sortable, filterable table for structured data display.

- **States**: loading (skeleton rows), loaded, empty (illustration + message + CTA), error
- **Responsive**: horizontal scroll on overflow; column priority (hide lower-priority columns on narrow screens)
- **Sorting**: clickable column headers with sort indicator; multi-column sort on shift+click
- **Pagination**: cursor-based (load more) or page-based configurable

### Provider Health Card

Expandable card showing provider status, latency, model list, and recent errors.

- **States**: healthy, degraded, down, disabled, configuring
- **Content**: status badge, average latency, uptime percentage, model count
- **Expanded**: model table with per-model latency and error rate, recent error log

## Do's and Don'ts

- Do: Show loading states that match the final layout dimensions (skeletons, not spinners)
- Do: Always show the last-known value in degraded/error states alongside a timestamp
- Do: Use the status badge pattern consistently across providers, API keys, budgets
- Do: Design for scanability — metrics first, details on demand
- Don't: Use color as the only indicator of state — always include text or icon
- Don't: Show raw JSON or internal error messages in the dashboard
- Don't: Auto-refresh without showing an indicator and allowing pause
- Don't: Block the page while fetching — stale data with a "last updated" timestamp is better than a loading spinner
- Don't: Show chart tooltips that overlap the data point being examined
