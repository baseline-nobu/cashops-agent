# CashOps Agent

CashOps Agent is an AI-powered cash-flow operations assistant for small businesses.

It connects financial events from PayPal, applies human review when important data is missing or uncertain, generates 30 / 60 / 90 day cash forecasts, and uses AI to explain cash-flow risk with traceable evidence.

## What it does

CashOps Agent turns invoice data into actionable cash-flow insight.

The current prototype can:

- Fetch invoice data from PayPal Sandbox
- Convert invoices into structured cash-flow events
- Detect missing or uncertain fields
- Request human confirmation when required
- Store human-confirmed values locally without writing back to PayPal
- Calculate deterministic 30 / 60 / 90 day forecasts
- Separate confirmed cash flow from draft-invoice scenarios
- Show the financial impact of human confirmation
- Generate AI-based cash risk reviews
- Explain why the AI reached its conclusion
- Link AI judgments to supporting evidence
- Automatically detect the reporting currency from PayPal data
- Support single-currency forecasts including JPY, USD, EUR, GBP and others
- Block mixed-currency aggregation until an FX conversion layer is available
- Fall back across multiple Gemini models if one model is temporarily unavailable

## Workflow

```text
PayPal Sandbox
      ↓
Cash Flow Events
      ↓
Human Review
      ↓
Deterministic Forecast Engine
      ↓
30 / 60 / 90 Day Forecast
      ↓
AI Risk Review
      ↓
Decision Basis + Issues + Questions + Recommended Actions