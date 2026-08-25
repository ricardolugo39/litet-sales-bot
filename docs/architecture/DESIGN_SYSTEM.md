# Dashboard Visual System

## Signature element

A single scope-color rail identifies the selected business context across page headers, KPI cards, navigation, focus states, and charts:

- Litet → cobalt
- Has10 → coral
- All → aubergine

The rest of the interface stays neutral and restrained so dense operational data remains easy to scan.

## Color tokens

| Token | Value | Use |
|---|---|---|
| Litet Cobalt | `#3154D8` | Litet scope and series |
| Has10 Coral | `#D5523F` | Has10 scope and series |
| All Aubergine | `#66507C` | Combined scope |
| Ink | `#172033` | Primary text and axes |
| Mist | `#F3F6FA` | Application and plotting surfaces |
| Signal Gold | `#D99A22` | Warnings and secondary emphasis |

## Typography

- Display and page headings: **Space Grotesk**, 600–700.
- Body and controls: **Inter**, 400–600.
- KPIs and tabular figures: **IBM Plex Mono**, 500–600, with tabular numerals.

The CSS includes system fallbacks if web fonts cannot load.

## Charts

All native charts use one Plotly template:

- transparent paper background and a subtle Mist plot surface;
- Ink labels;
- light horizontal gridlines and suppressed chart borders;
- unified dark hover cards;
- compact margins and horizontal legends;
- scope-aware colorways led by the selected brand color.

## Controls

The sidebar presents one consistently named control: **Filter by brand**. Inputs use a compact 10px radius, visible Ink border, scope-colored focus ring, and scope tint for the active value. Navigation and the filter share the same selected-scope language.
