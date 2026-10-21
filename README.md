
# CashOps Agent

CashOps Agent helps small businesses see potential cash pressure earlier by turning invoice data into a human-reviewed 30 / 60 / 90-day cash outlook and explainable AI risk insights.

The current prototype uses PayPal Sandbox invoice data as its financial data source.

Its architecture intentionally separates three responsibilities:

- **Deterministic logic** calculates financial balances and the 30 / 60 / 90-day outlook.
- **Human Review** confirms missing or uncertain financial information.
- **NVIDIA Nemotron** interprets the established evidence and explains risk, uncertainty, unresolved issues, and recommended actions.

The AI model does not calculate balances or invent financial values.

## Live Demo

https://cashops-agent.streamlit.app

The deployed Streamlit demo is publicly accessible and does not require login credentials.

## Demo Video

https://youtu.be/BHTo21CDJMw

The demo video shows the deployed application running live, including PayPal data loading, human review, cash forecasting, and AI Risk Review.

## What It Does

CashOps Agent turns invoice data into actionable cash-flow insight.

The current prototype can:

- Fetch invoice data from PayPal Sandbox
- Convert invoices into structured cash-flow events
- Detect missing or uncertain fields
- Request human confirmation when required
- Store human-confirmed values locally without writing back to PayPal
- Calculate deterministic 30 / 60 / 90-day cash outlooks
- Separate confirmed cash flow from draft-invoice scenarios
- Show the financial impact of human confirmation
- Generate AI-assisted cash-risk reviews
- Explain the basis of AI risk judgments
- Show Cash Risk and Data Confidence
- Identify unresolved issues
- Generate follow-up questions
- Recommend next actions
- Automatically detect the reporting currency from PayPal data
- Support single-currency forecasts including JPY, USD, EUR, GBP, and others
- Block mixed-currency aggregation until an FX conversion layer is available

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
30 / 60 / 90 Day Cash Outlook
      ↓
NVIDIA Nemotron
via Nebius Token Factory
      ↓
Cash Risk
Data Confidence
Issues
Questions
Recommended Actions
```

## Human-in-the-Loop Design

CashOps Agent does not guess when important financial information is missing or uncertain.

If invoice data requires clarification, the application sends the item to Human Review.

The confirmed information is then used to update the forecast.

This keeps uncertain data separate from confirmed financial assumptions and makes the decision process traceable.

## Deterministic Financial Calculations

Cash balances and 30 / 60 / 90-day outlooks are calculated by the application itself.

The AI model does not calculate balances or invent financial values.

This separation is intentional:

- Deterministic logic handles financial calculations
- Human Review handles missing or uncertain information
- AI interprets the established evidence

This improves explainability and reduces the risk of AI-generated financial errors.

## Why NVIDIA Nemotron?

CashOps Agent uses **NVIDIA Nemotron-3.5-Lightning through Nebius Token Factory** as an interpretation and decision-support layer.

The purpose of the model is not to replace deterministic financial calculations.

Instead, Nemotron receives structured forecast evidence produced by the application and interprets:

- Cash Risk
- Data Confidence
- Unresolved Issues
- Follow-up Questions
- Recommended Actions

This separation allows the application to keep financial calculations deterministic while using an AI model for the parts where language understanding, contextual interpretation, and explanation provide additional value.

Nebius Token Factory provides the hosted inference endpoint used by the deployed application.

## NVIDIA Nemotron

CashOps Agent uses:

**NVIDIA Nemotron-3.5-Lightning**

The model is used for AI Risk Review.

It receives structured forecast evidence and returns analysis including:

- Cash Risk
- Data Confidence
- Issues
- Follow-up Questions
- Recommended Actions

The AI output is used for interpretation and explanation only.

## Nebius Token Factory

CashOps Agent uses Nebius Token Factory as the hosted inference layer for NVIDIA Nemotron.

Nebius Token Factory provides the API endpoint used by the Streamlit application to send structured forecast evidence to the model and receive structured AI risk analysis.

The application uses an OpenAI-compatible API interface.

## Current Limitations

This project is a hackathon prototype and intentionally has a limited scope.

- The current prototype uses **PayPal Sandbox** rather than real customer financial data.
- The opening balance is a configured assumption for the demonstration.
- The current prototype focuses primarily on **invoice-driven cash events** and does not represent a complete accounting or treasury system.
- Payroll, taxes, bank-account transactions, and full expense integrations are not included in the current prototype.
- Mixed-currency aggregation is intentionally blocked until a proper FX conversion layer is implemented.
- Human confirmation is required when important financial information is missing or uncertain.
- NVIDIA Nemotron provides interpretation and recommendations; it does not autonomously execute financial transactions.

These limitations are intentional. CashOps Agent prioritizes traceable assumptions and reliable financial calculations rather than asking an AI model to invent missing financial data.

## How to Test

1. Open the live demo:  
   https://cashops-agent.streamlit.app

2. Click **Refresh from PayPal**

3. Review the imported PayPal Sandbox invoices

4. Check the **Human Review** section

5. Confirm any missing or uncertain information if required

6. Review the deterministic **30 / 60 / 90 Day Cash Outlook**

7. Review the impact of human confirmation on the scenario forecast

8. Click **Run AI Risk Review**

9. Review:
   - Cash Risk
   - Data Confidence
   - Issues
   - Questions
   - Recommended Actions

No login credentials are required to test the deployed demo.

## Local Setup

Clone the repository:

```bash
git clone https://github.com/baseline-nobu/cashops-agent.git
cd cashops-agent
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the Streamlit application:

```bash
streamlit run app.py
```

## Environment Variables

The application uses the following environment variables:

```text
PAYPAL_CLIENT_ID
PAYPAL_CLIENT_SECRET
PAYPAL_BASE_URL
NEBIUS_API_KEY
OPENING_BALANCE
DEFAULT_CURRENCY
```

API keys and credentials are not stored in this repository.

For the deployed Streamlit demo, secrets are configured securely in the hosting environment.

## Main Files

```text
app.py
paypal_fetch.py
forecast.py
human_review.py
ai_review.py
requirements.txt
```

### app.py

Main Streamlit application and user interface.

### paypal_fetch.py

Fetches invoice data from PayPal Sandbox and converts the source data into application-ready financial events.

### forecast.py

Calculates deterministic 30 / 60 / 90-day cash outlooks.

### human_review.py

Handles missing or uncertain financial information and stores human-confirmed values locally.

### ai_review.py

Sends established forecast evidence to NVIDIA Nemotron through Nebius Token Factory and processes the structured AI risk response.

## Technology Stack

- Python
- Streamlit
- PayPal Sandbox
- PayPal Invoicing API
- NVIDIA Nemotron-3.5-Lightning
- Nebius Token Factory
- OpenAI-compatible API
- Pandas
- Altair

## Repository

https://github.com/baseline-nobu/cashops-agent

## License

MIT License
