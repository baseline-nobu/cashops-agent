import os
import json
import time

from google import genai


# =========================================================
# Environment
# =========================================================

def load_env(path=".env.local"):
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            key, value = line.split("=", 1)
            os.environ[key] = value


load_env()


client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


# =========================================================
# Model fallback
# =========================================================

MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]


def is_retryable_model_error(error):
    text = str(error).lower()

    retryable_markers = [
        "503",
        "unavailable",
        "high demand",
        "temporarily",
        "resource exhausted",
        "429",
    ]

    return any(
        marker in text
        for marker in retryable_markers
    )


def generate_with_fallback(prompt):
    errors = []

    for model_name in MODEL_CANDIDATES:

        # Small retry loop for temporary spikes.
        for attempt in range(2):

            try:
                response = (
                    client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                )

                if response is None:
                    raise RuntimeError(
                        f"{model_name} returned no response."
                    )

                response_text = (
                    response.text
                    or ""
                ).strip()

                if not response_text:
                    raise RuntimeError(
                        f"{model_name} returned empty text."
                    )

                return (
                    response,
                    model_name,
                )

            except Exception as e:
                errors.append(
                    f"{model_name}: {e}"
                )

                if not is_retryable_model_error(e):
                    raise

                if attempt == 0:
                    time.sleep(1.5)

        # Both attempts failed:
        # continue to the next model.

    raise RuntimeError(
        "All Gemini fallback models failed. "
        + " | ".join(errors)
    )


# =========================================================
# Currency
# =========================================================

CURRENCY_SYMBOLS = {
    "JPY": "¥",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AUD": "A$",
    "CAD": "C$",
    "CHF": "CHF ",
    "CNY": "CN¥",
    "KRW": "₩",
    "SGD": "S$",
    "NZD": "NZ$",
}


ZERO_DECIMAL_CURRENCIES = {
    "JPY",
    "KRW",
}


def detect_currency(events):
    currencies = {
        event.get("currency")
        for event in events
        if event.get("currency")
    }

    if len(currencies) == 1:
        return next(iter(currencies))

    if not currencies:
        return "JPY"

    return "MIXED"


def format_money(
    value,
    currency
):
    value = float(value)

    symbol = CURRENCY_SYMBOLS.get(
        currency,
        f"{currency} "
    )

    negative = value < 0
    absolute = abs(value)

    if currency in ZERO_DECIMAL_CURRENCIES:
        text = (
            f"{symbol}"
            f"{absolute:,.0f}"
        )
    else:
        text = (
            f"{symbol}"
            f"{absolute:,.2f}"
        )

    if negative:
        return f"-{text}"

    return text


# =========================================================
# Evidence
# =========================================================

def build_evidence(
    events,
    opening_balance,
    confirmed_forecast,
    scenario_forecast,
):
    currency = detect_currency(
        events
    )

    evidence = []

    evidence.append({
        "id": "E1",
        "fact": (
            "Opening balance is "
            f"{format_money(opening_balance, currency)} "
            f"({currency})."
        ),
    })


    evidence.append({
        "id": "E2",
        "fact": (
            "Confirmed forecast balances are "
            f"30 days: "
            f"{format_money(confirmed_forecast[30], currency)}, "
            f"60 days: "
            f"{format_money(confirmed_forecast[60], currency)}, "
            f"90 days: "
            f"{format_money(confirmed_forecast[90], currency)}."
        ),
    })


    evidence.append({
        "id": "E3",
        "fact": (
            "Scenario forecast including eligible draft invoices is "
            f"30 days: "
            f"{format_money(scenario_forecast[30], currency)}, "
            f"60 days: "
            f"{format_money(scenario_forecast[60], currency)}, "
            f"90 days: "
            f"{format_money(scenario_forecast[90], currency)}."
        ),
    })


    draft_events = [
        event
        for event in events
        if event.get("status") == "DRAFT"
    ]

    evidence.append({
        "id": "E4",
        "fact": (
            f"There are "
            f"{len(draft_events)} "
            "draft invoice event(s)."
        ),
    })


    needs_confirmation = [
        event
        for event in events
        if event.get("needs_confirmation")
    ]

    evidence.append({
        "id": "E5",
        "fact": (
            f"{len(needs_confirmation)} "
            "event(s) currently require human confirmation."
        ),
    })


    missing_details = []

    for event in events:
        missing_fields = (
            event.get(
                "missing_fields",
                []
            )
        )

        if not missing_fields:
            continue

        amount = format_money(
            event.get(
                "amount",
                0
            ),
            event.get("currency")
            or currency
        )

        missing_details.append(
            (
                f"Event "
                f"{event.get('source_id')} "
                f"for {amount} "
                f"is missing: "
                f"{', '.join(missing_fields)}."
            )
        )


    if missing_details:
        missing_fact = " ".join(
            missing_details
        )
    else:
        missing_fact = (
            "No currently loaded event "
            "has unresolved required fields."
        )


    evidence.append({
        "id": "E6",
        "fact": missing_fact,
    })


    human_confirmed = [
        event
        for event in events
        if event.get(
            "human_confirmed_due_date"
        )
    ]


    evidence.append({
        "id": "E7",
        "fact": (
            f"{len(human_confirmed)} "
            "event(s) contain due dates "
            "confirmed by a human inside CashOps Agent."
        ),
    })


    return evidence


# =========================================================
# AI review
# =========================================================

def run_ai_review(
    events,
    opening_balance,
    confirmed_forecast,
    scenario_forecast,
):
    currency = detect_currency(
        events
    )

    evidence = build_evidence(
        events=events,
        opening_balance=opening_balance,
        confirmed_forecast=confirmed_forecast,
        scenario_forecast=scenario_forecast,
    )


    payload = {
        "reporting_currency":
        currency,

        "events":
        events,

        "opening_balance":
        opening_balance,

        "confirmed_forecast":
        confirmed_forecast,

        "scenario_forecast":
        scenario_forecast,

        "evidence":
        evidence,
    }


    prompt = f"""
You are the AI reasoning layer of CashOps Agent,
a cash-flow operations assistant for small businesses.

The reporting currency for this review is:

{currency}

You must analyze ONLY the supplied data and evidence.

Important rules:

- Do not calculate or invent new cash balances.
- Use the forecast values supplied by CashOps Agent.
- Treat DRAFT invoices as uncertain future cash flow.
- Do not treat a human-confirmed due date as proof that
  a DRAFT invoice is guaranteed cash.
- Human confirmation improves data completeness,
  but does not automatically make an invoice finalized.
- Explain uncertainty clearly.
- Use evidence IDs for every important judgment.
- Do not cite evidence that does not support the statement.
- Do not invent expenses, liabilities, payroll, taxes,
  bank balances, or transactions that were not supplied.
- Keep explanations concise and practical.
- When mentioning money, preserve the reporting currency.
- Do not append ".0" to whole-number monetary values.
- Prefer readable monetary notation such as
  ¥500,000, $5,000.00, or €5,000.00.

Return ONLY valid JSON using exactly this structure:

{{
  "cash_risk": "low | medium | high",
  "data_confidence": "low | medium | high",
  "summary": "short summary",
  "decision_basis": [
    {{
      "evidence_ids": ["E1", "E2"],
      "finding": "what the evidence shows",
      "why_it_matters": "why this matters for cash operations"
    }}
  ],
  "issues": [
    {{
      "issue": "issue description",
      "evidence_ids": ["E5"]
    }}
  ],
  "questions_for_user": [
    {{
      "question": "question",
      "evidence_ids": ["E6"]
    }}
  ],
  "recommended_actions": [
    {{
      "action": "action",
      "evidence_ids": ["E6"]
    }}
  ]
}}

DATA:

{json.dumps(
    payload,
    ensure_ascii=False,
    indent=2
)}
"""


    response, used_model = (
        generate_with_fallback(
            prompt
        )
    )


    text = (
        response.text
        or ""
    ).strip()


    # Remove possible Markdown fences.
    if text.startswith(
        "```json"
    ):
        text = text[7:]

    elif text.startswith(
        "```"
    ):
        text = text[3:]


    if text.endswith(
        "```"
    ):
        text = text[:-3]


    text = text.strip()


    result = json.loads(
        text
    )


    # Deterministic evidence and model provenance.
    result["evidence"] = evidence
    result["reporting_currency"] = currency
    result["model_used"] = used_model


    return result