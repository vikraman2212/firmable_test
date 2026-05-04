# Phase 4 Stories — UI Shell, State, Search, and Result Cards (P4-T01 to P4-T04)

## Wireframe Reference

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Company Search Dashboard                                                    │
├─────────────────────────────────┬───────────────────────────────────────────┤
│ Filters Panel                   │ Results Panel                             │
│                                 │                                           │
│ ┌─────────────────────────────┐ │ ┌─────────────────────────────────────┐   │
│ │ Free Text Search            │ │ │ Search Results (1,247 found)        │   │
│ │ [Search companies...]       │ │ │                                     │   │
│ │                             │ │ │ ┌─────────────────────────────────┐ │   │
│ │ ┌─────────────────────────┐ │ │ │ │ IBM                             │ │   │
│ │ │ Industry                │ │ │ │ │ Domain: ibm.com                 │ │   │
│ │ │ ☑ Information Technology│ │ │ │ │ Industry: Information Technology│ │   │
│ │ │ ☐ Financial Services    │ │ │ │ │ Location: New York, NY, US      │ │   │
│ │ │ ☐ Healthcare            │ │ │ │ │ Founded: 1911 | Size: 10001+    │ │   │
│ │ └─────────────────────────┘ │ │ │ │ Employees: 274,047              │ │   │
│ │                             │ │ │ └─────────────────────────────────┘ │   │
│ │ ┌─────────────────────────┐ │ │ │                                     │   │
│ │ │ Company Size            │ │ │ │ ┌─────────────────────────────────┐ │   │
│ │ │ ☑ Large (10001+)        │ │ │ │ │ Tata Consultancy Services       │ │   │
│ │ │ ☐ Medium (1000-10000)   │ │ │ │ │ Domain: tcs.com                 │ │   │
│ │ │ ☐ Small (<1000)         │ │ │ │ │ Industry: Information Technology│ │   │
│ │ └─────────────────────────┘ │ │ │ │ Location: Bombay, Maharashtra   │ │   │
│ │                             │ │ │ │ Founded: 1968 | Size: 10001+    │ │   │
│ │ ┌─────────────────────────┐ │ │ │ │ Employees: 190,771              │ │   │
│ │ │ Location                │ │ │ │ └─────────────────────────────────┘ │   │
│ │ │ Country: [United States]│ │ │ │                                     │   │
│ │ │ City: [New York]        │ │ │ │ [Previous] 1 2 3 ... 50 [Next]    │   │
│ │ └─────────────────────────┘ │ │ │                                     │   │
│ │                             │ │ │ Sort by: Relevance | Name | Size   │   │
│ │ ┌─────────────────────────┐ │ │ └─────────────────────────────────────┘   │
│ │ │ Founding Year           │ │                                             │
│ │ │ From: [1900]            │ │                                             │
│ │ │ To:   [2000]            │ │                                             │
│ │ └─────────────────────────┘ │                                             │
│ │                             │                                             │
│ │ ┌─────────────────────────┐ │                                             │
│ │ │ Tags                    │ │                                             │
│ │ │ ☑ My Tags               │ │                                             │
│ │ │ ☐ Shared Lists          │ │                                             │
│ │ └─────────────────────────┘ │                                             │
│ │                             │                                             │
│ [Clear All] [Apply Filters]   │                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Story P4-T01: Static UI Shell

- **Backlog mapping**: `P4-T01`
- **Persona**: Front-End Developer, Sales Researcher
- **Story**: As a front-end developer, I want a static HTML shell with the two-panel dashboard layout so there is a stable DOM structure for wiring search and result rendering against.

### Acceptance Criteria

- The page renders a two-column layout: a fixed-width left filters panel and a flexible right results panel.
- The filters panel contains a `<form>` wrapping labelled sections for: Free Text Search input, Industry (checkbox group), Company Size (checkbox group), Location (Country text input, City text input), Founding Year (From/To number inputs), and Tags (checkbox group — placeholder, not wired to API in this slice).
- All filter inputs are native form elements (`<input>`, `<select>`, `<checkbox>`) so their current values are readable directly from the DOM without a separate state object.
- The results panel contains a result count heading and a result list container.
- The filters panel has Clear All and Apply Filters buttons.
- The layout is usable at desktop width (≥ 1024px) and readable on a 768px tablet viewport without horizontal scrolling.
- No JavaScript framework or build step is required — plain HTML with `id`/class hooks for JS targeting.
- No live API calls are wired in this task; all interactive elements are inert placeholders.

---

## Story P4-T02: Explicit Search Requests

- **Backlog mapping**: `P4-T02`
- **Persona**: Front-End Developer, Sales Researcher
- **Story**: As a sales researcher, I want search to fire only when I press Enter or click Apply Filters so I control when the query runs rather than triggering a request on every keystroke.

### Acceptance Criteria

- Search fires when the user presses Enter while focused in the free-text input.
- Search fires when the user clicks the Apply Filters button.
- There is no debounce or live-search-as-you-type behaviour.
- The search logic lives in a separate `web/app.js` file (plain JS, no build step, no framework).
- The request body is assembled by reading form field values at the moment of submission: `query` from the text input, `industry` from checked Industry checkboxes, `size_range` from checked Company Size checkboxes, `country` and `city` from the Location inputs, `year_founded_gte` and `year_founded_lte` from the Founding Year inputs.
- Empty or unchecked fields are omitted from the request body rather than sent as empty strings or empty arrays.
- A visible loading indicator appears in the results panel while the request is in flight.
- On a non-2xx response or network failure the results panel shows a human-readable error message; the loading indicator is cleared.
- On a successful response the results panel is updated and the loading state is cleared.
- Clear All resets all form fields to their empty defaults; it does not automatically re-run the search.

---

## Story P4-T03: Result Cards and Empty/Error States

- **Backlog mapping**: `P4-T03`
- **Persona**: Sales Researcher, Business Analyst
- **Story**: As a sales researcher, I want each result rendered as a structured card so I can quickly scan company identity, location, size, and founding year without opening a detail view.

### Acceptance Criteria

- Each result card displays: company name (prominent heading), domain, industry, location as "City, Region, Country" (omitting blank parts), founded year, size_range, and current_employee_estimate (formatted with thousands separators).
- Fields that are null or absent are omitted from the card without leaving a blank line or placeholder label.
- The result count heading reflects the `total` from the API response (e.g. "1,247 results found").
- When the API returns zero results, the results panel shows a clear empty-state message (e.g. "No companies matched your search. Try adjusting your filters.").
- When the API returns an error, the results panel shows a concise error message; it does not show a blank panel or a raw HTTP status string.
- Cards are rendered in the order returned by the API.
- The result list is fully replaced on each new response — stale cards from the previous query are not left in the DOM.

---

## Scope Notes

- **P4-T02 (JS state model)** is removed — filter state lives in native form fields; no separate state object is needed for this slice.
- **P4-T04 (sort control)**, **P4-T05 (facets + pagination wiring)**, and **P4-T06 (Docker serving)** are explicitly out of scope for this slice.
- The Tags filter section in the shell (P4-T01) is rendered as an inert placeholder; it is not wired to any API call in this slice.
- The Industry and Company Size checkbox lists are hardcoded in the HTML for this slice; facet-driven population is deferred to P4-T05.
