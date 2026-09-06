# InvestMent Monitor Design Context

## Overview

InvestMent Monitor is a read-only paper-trading observatory for cross-exchange perpetual arbitrage. Its product register is a dense financial operations console: quiet, factual, and easy to audit at a glance. The signature is not decorative motion; it is the causal chain from **opportunity → risk budget → open pair → realized result** remaining visible even when there is no open trade.

The interface must never resemble a casino, exchange order-entry ticket, or promotional crypto landing page. Green/red are semantic only. Amber means caution, hypothetical, unavailable, or filtered—not profit opportunity hype.

## Colors

Runtime CSS variables in `monitoring-web/app/globals.css` are the canonical token source:

- Background `#070908`
- Surface `#0d100f`; raised surface `#111513`
- Primary text `#f3f5f1`; muted `#8d968e`; secondary muted `#626b64`
- Profit / LONG / healthy `#62e39a`
- Loss / SHORT / degraded `#ff7878`
- Caution / simulation / unavailable `#e8c56e`

## Typography

Use the existing system sans stack for headings and explanatory copy. Use `ui-monospace, SFMono-Regular, Menlo, monospace` for prices, quantities, PnL, leverage, spreads, and tabular diagnostics. Tabular numerals stay enabled globally.

## Layout

Desktop is information-dense with a 1480px maximum shell. Primary account KPIs come first, followed by actual modeled risk, opportunity diagnostics, live positions, what-if capacity, realized effectiveness, and the execution ledger. Tables own horizontal overflow on narrow screens; the document retains normal vertical scrolling.

## Elevation & Depth

Use one-pixel low-contrast borders and slight surface gradients. Avoid shadows except semantic inset accents on LONG/SHORT legs. Hierarchy comes from grouping and density rather than floating cards.

## Shapes

Panels use the established 12px radius, inner groups 7–9px, and status pills only for compact state labels. Do not introduce large pill-shaped controls or decorative bubbles.

## Components

- **KPI strip:** compact factual account state; never mixes realized and estimated PnL without labeling.
- **Risk budget:** shows only engine-modeled leverage, initial margin, collateral, caps, and invariant health.
- **Opportunity Radar:** bounded native table explaining trade/reject decisions; no raw exchange payloads.
- **Live pair card:** visually separates LONG and SHORT legs and uses executable close VWAP.
- **What-if capacity:** amber-framed simulation language; never presented as an actual order or expected return.
- **Ledger:** native read-only table; OPEN values are estimated, CLOSED values are realized.

## Do's and Don'ts

- Do keep PAPER / READ ONLY boundaries visible.
- Do show `Unavailable` / `Not modeled` when the engine lacks evidence.
- Do keep zero-position states informative through the radar and capacity model.
- Do preserve keyboard focus on what-if buttons and native table semantics.
- Don't infer liquidation, maintenance margin, funding, or future PnL.
- Don't use animation, flashing prices, oversized gradients, or gamified green/red surfaces.
