# AQT Design

Mode: **Operate**. World: **Ledger Desk**.

## Brief
Single-operator execution console for SIM / LIVE automation.
Job: control the system first; inspect account second. Not a marketing dashboard.

## Tokens
| Role | Value |
|---|---|
| Paper | `#F1F2F4` |
| Surface | `#FFFFFF` |
| Ink | `#14161C` |
| Ink muted | `#5C6370` |
| Line | `#DDE0E6` |
| Accent | `#1F4B43` |
| Accent soft | `#E8F0EE` |
| LIVE | `#A33B1A` |
| LIVE soft | `#F8EBE6` |
| OK | `#1F6B45` |

## Type
- UI: **Sora** (one family for chrome and headings)
- Data: **JetBrains Mono** only for numbers / IDs / gateways
- Sentence case. No tracked ALL-CAPS eyebrows. No “OPS CONSOLE” costume.

## Layout
```
[sider]  title ................ status chips
         ┌─ Run ──────────────────────────┐
         │ SIM controls · Tick · LIVE     │
         └────────────────────────────────┘
         ┌─ Account (ledger rows) ────────┐
         │ Equity / Cash / MV / PnL       │
         └────────────────────────────────┘
         ┌─ Gateway ──────────────────────┐
```
- Controls before vanity metrics
- Ledger rows instead of four equal KPI cards
- Elevation: border OR soft shadow, never both as default

## Motion
- 160ms state feedback only
- No page-load choreography

## Refuse
Glass, gradient text, left accent bars, SaaS card kits, purple accents.
