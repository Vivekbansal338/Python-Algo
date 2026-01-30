# V6 Trading Bot - TUI Summary and Recommendation

## Current AI: kimi k2.5

---

## Current TUI Implementation

**Library**: Rich (textual/rich)

**Current Usage**:
```python
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

# 4 FPS refresh using Live context manager
with Live(self.ui.render(), refresh_per_second=4, screen=True) as live:
    while self.running:
        # Update logic
        self.ui.update(ui_state)
        live.update(self.ui.render())
```

**Pros**:
- Simple, easy to implement
- Already working in production
- Excellent for read-only dashboards
- Great styling, colors, tables out-of-box
- Good performance at 4 FPS

**Cons**:
- Limited interactivity (no buttons, forms, complex widgets)
- Layout can be rigid for complex UIs
- No built-in scrolling for large datasets
- No async/await support for cleaner data handling

---

## TUI Requirements

- Real-time dashboard at 4 FPS (250ms)
- 50+ stocks and ~15 sectors visible
- Scrollable tables for large datasets
- Cross-platform: Windows/Linux/Mac
- Maintainable by a single developer
- Future interactivity (pause/resume, manual orders, parameter adjustments)

---

## TUI Library Options

### 1. Rich (Current)
**Type**: Display-focused library
**Interactivity**: None
**Async**: No
**Strengths**: Simple, stable, great styling
**Limitations**: No scrolling or interaction

### 2. Textual (Recommended)
**Type**: Full TUI framework by Rich author
**Interactivity**: High
**Async**: Yes
**Strengths**: DataTable, scrolling, sorting, events, reactive model
**Migration**: Easy (similar styling to Rich)

### 3. PyTermGUI
**Type**: Modern TUI framework
**Interactivity**: High
**Async**: Partial
**Limitations**: Newer, less documentation

### 4. Urwid
**Type**: Full TUI library
**Interactivity**: High
**Async**: Yes
**Limitations**: Steeper learning curve, more boilerplate

### 5. Blessed
**Type**: Low-level terminal handling
**Interactivity**: Manual
**Async**: Manual
**Limitations**: Requires building everything from scratch

---

## Recommendation from kimi k2.5

**My Suggestion: Textual**

**Rationale**:
1. Easy migration from Rich (same author, similar styling)
2. Future-proof: interactive controls can be added
3. Async support for WebSocket-driven updates
4. Built-in scrolling and sortable tables
5. Active development and strong ecosystem

**Migration Path**:
- Phase 1: Port layout and tables (1-2 days)
- Phase 2: Add scrolling and sorting
- Phase 3: Add controls (pause/resume, parameter inputs)
- Phase 4: Add manual order entry

---

## Recommendation from opencode

**Recommended TUI Library: Textual**

### Why Textual is Best

**Pain Points Solved**:
- Scrollable tables for 50+ symbols
- Native async support for real-time updates
- Event-driven architecture for cleaner code
- Built-in widgets for future interactive controls

**Migration Effort**: 4-8 hours for feature-parity conversion

### Widget Mapping

| Section | Rich | Textual | Benefit |
|---------|------|---------|---------|
| Header | Panel + Text | Header/Static | Auto layout |
| Sectors | Table | DataTable | Sorting, scrolling |
| Signals | Table | DataTable | Selection, resize |
| Portfolio | Table | DataTable | Real-time updates |
| Logs | Panel + Text | RichLog | Auto-scroll |

### Example Structure

```python
class TradingBotApp(App):
    CSS = """
    Header {height: 3;}
    Scanner {width: 60%;}
    Portfolio {width: 40%;}
    Logs {height: 30%;}
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Scanner(),
            Vertical(Portfolio(), Logs())
        )
```

### Migration Plan

**Phase 1 (Day 1)**
- Port tables to DataTable
- Keep existing styling
- Maintain 4 FPS refresh

**Phase 2 (Day 2-3)**
- Add sorting and scrolling
- Add keyboard shortcuts

**Phase 3 (Week 2)**
- Add control panel
- Add manual order entry

### Risks and Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Migration bugs | Medium | High | Regression testing |
| Performance regression | Low | Medium | Benchmark 4 FPS |
| Learning curve | Medium | Low | Follow phased plan |

---

## Final Verdict

**Go with Textual** for the V6 TUI.

**Stick with Rich** only if the UI will remain read-only and the 15-signal limit is acceptable.

---

## Prompt for Other AI Assistants

**Task**:
1. Evaluate TUI options (Rich vs Textual vs others)
2. Recommend the best library for this use case
3. Estimate migration effort (hours/days)
4. Identify risks and mitigation
5. If recommending Textual, suggest widget mapping and layout

**Constraints**:
- Cross-platform (Windows/Linux/Mac)
- Real-time updates (WebSocket ticks)
- 50-100 symbols with good performance
- Maintainable by a single developer

---

**Document Created By**: kimi k2.5
**Document Updated By**: opencode
**Date**: 2026-01-30
