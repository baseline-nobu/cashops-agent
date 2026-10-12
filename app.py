import os
import json
import base64
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from ai_review import run_ai_review
from human_review import (
    apply_overrides,
    save_due_date_override,
    remove_due_date_override,
)


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

PAYPAL_BASE_URL = os.environ["PAYPAL_BASE_URL"]
PAYPAL_CLIENT_ID = os.environ["PAYPAL_CLIENT_ID"]
PAYPAL_CLIENT_SECRET = os.environ["PAYPAL_CLIENT_SECRET"]

DEFAULT_OPENING_BALANCE = float(
    os.environ.get(
        "OPENING_BALANCE",
        "500000",
    )
)

DEFAULT_CURRENCY = os.environ.get(
    "DEFAULT_CURRENCY",
    "JPY",
).upper()

CACHE_FILE = "cashflow_events.json"


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
    currencies = sorted({
        event.get("currency")
        for event in events
        if event.get("currency")
    })

    if not currencies:
        return DEFAULT_CURRENCY

    if len(currencies) == 1:
        return currencies[0]

    return None


def money(value, currency):
    value = float(value)

    symbol = CURRENCY_SYMBOLS.get(
        currency,
        f"{currency} ",
    )

    negative = value < 0
    absolute = abs(value)

    if currency in ZERO_DECIMAL_CURRENCIES:
        text = f"{symbol}{absolute:,.0f}"
    else:
        text = f"{symbol}{absolute:,.2f}"

    if negative:
        return f"-{text}"

    return text


def money_delta(value, currency):
    value = float(value)

    sign = "+" if value > 0 else ""

    if currency in ZERO_DECIMAL_CURRENCIES:
        return f"{sign}{value:,.0f} {currency}"

    return f"{sign}{value:,.2f} {currency}"


# =========================================================
# PayPal
# =========================================================

def get_paypal_access_token():
    credentials = base64.b64encode(
        (
            f"{PAYPAL_CLIENT_ID}:"
            f"{PAYPAL_CLIENT_SECRET}"
        ).encode()
    ).decode()

    request = urllib.request.Request(
        f"{PAYPAL_BASE_URL}/v1/oauth2/token",
        data=urllib.parse.urlencode(
            {
                "grant_type":
                "client_credentials"
            }
        ).encode(),
        headers={
            "Authorization":
            f"Basic {credentials}",
            "Content-Type":
            "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request
    ) as response:
        data = json.load(response)

    return data["access_token"]


def paypal_get(url, token):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization":
            f"Bearer {token}"
        },
    )

    with urllib.request.urlopen(
        request
    ) as response:
        return json.load(response)


def fetch_paypal_events():
    token = get_paypal_access_token()

    invoice_list = paypal_get(
        (
            f"{PAYPAL_BASE_URL}"
            "/v2/invoicing/invoices"
            "?page=1"
            "&page_size=100"
            "&total_required=true"
        ),
        token,
    )

    events = []

    for invoice in invoice_list.get(
        "items",
        [],
    ):
        invoice_id = invoice.get("id")

        detail = paypal_get(
            (
                f"{PAYPAL_BASE_URL}"
                "/v2/invoicing/invoices/"
                f"{invoice_id}"
            ),
            token,
        )

        amount = detail.get(
            "amount",
            {},
        )

        invoice_detail = detail.get(
            "detail",
            {},
        )

        payment_term = invoice_detail.get(
            "payment_term",
            {},
        )

        recipients = detail.get(
            "primary_recipients",
            [],
        )

        counterparty = None

        if recipients:
            counterparty = (
                recipients[0]
                .get(
                    "billing_info",
                    {},
                )
                .get(
                    "email_address"
                )
            )

        due_date = payment_term.get(
            "due_date"
        )

        missing_fields = []

        if not due_date:
            missing_fields.append(
                "due_date"
            )

        if not counterparty:
            missing_fields.append(
                "counterparty"
            )

        events.append({
            "source":
            "paypal",

            "source_id":
            invoice_id,

            "type":
            "invoice_receivable",

            "direction":
            "inflow",

            "amount":
            amount.get("value"),

            "currency":
            amount.get(
                "currency_code"
            ),

            "counterparty":
            counterparty,

            "status":
            detail.get("status"),

            "due_date":
            due_date,

            "needs_confirmation":
            bool(missing_fields),

            "missing_fields":
            missing_fields,
        })

    return events


# =========================================================
# Cache
# =========================================================

def save_events(events):
    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            events,
            f,
            indent=2,
            ensure_ascii=False,
        )


def load_events():
    if not os.path.exists(
        CACHE_FILE
    ):
        return []

    with open(
        CACHE_FILE,
        encoding="utf-8",
    ) as f:
        return json.load(f)


# =========================================================
# Forecast
# =========================================================

def event_amount(event):
    value = event.get("amount")

    if value in (
        None,
        "",
    ):
        return 0.0

    return float(value)


def signed_event_value(event):
    amount = event_amount(event)

    if (
        event.get("direction")
        == "outflow"
    ):
        return -amount

    return amount


def calculate_balance(
    events,
    days,
    opening_balance,
    reporting_currency,
    include_drafts=False,
):
    today = date.today()

    end_date = (
        today
        + timedelta(days=days)
    )

    balance = float(
        opening_balance
    )

    for event in events:

        if (
            event.get("currency")
            != reporting_currency
        ):
            continue

        if event.get(
            "needs_confirmation"
        ):
            continue

        due_text = event.get(
            "due_date"
        )

        if not due_text:
            continue

        try:
            due_date = datetime.strptime(
                due_text,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            continue

        if not (
            today
            <= due_date
            <= end_date
        ):
            continue

        if (
            event.get("status")
            == "DRAFT"
            and not include_drafts
        ):
            continue

        balance += signed_event_value(
            event
        )

    return balance


# =========================================================
# Page
# =========================================================

st.set_page_config(
    page_title="CashOps Agent",
    page_icon="💰",
    layout="wide",
)

st.title(
    "CashOps Agent"
)

st.caption(
    "PayPal → Human Review → "
    "AI Risk Review → "
    "30 / 60 / 90 Day Cash Forecast"
)


# =========================================================
# PayPal data
# =========================================================

raw_events = load_events()

if st.button(
    "🔄 Refresh from PayPal",
    type="primary",
):
    try:
        with st.spinner(
            "Fetching PayPal data..."
        ):
            raw_events = (
                fetch_paypal_events()
            )

            save_events(
                raw_events
            )

        st.session_state.pop(
            "ai_review",
            None,
        )

        st.success(
            "PayPal sync complete: "
            f"{len(raw_events)} "
            "invoice(s)"
        )

    except Exception as e:
        st.error(
            "PayPal sync failed: "
            f"{e}"
        )


events = apply_overrides(
    raw_events
)

REPORTING_CURRENCY = (
    detect_currency(
        events
    )
)


# =========================================================
# Mixed-currency safety
# =========================================================

if REPORTING_CURRENCY is None:
    currencies = sorted({
        event.get("currency")
        for event in events
        if event.get("currency")
    })

    st.error(
        "Multiple currencies detected: "
        + ", ".join(currencies)
    )

    st.warning(
        "CashOps Agent does not add "
        "different currencies together. "
        "An FX conversion layer is required "
        "before a consolidated forecast "
        "can be calculated."
    )

    st.dataframe(
        events,
        width="stretch",
        hide_index=True,
    )

    st.stop()


# =========================================================
# Sidebar
# =========================================================

with st.sidebar:

    st.header(
        "Forecast Settings"
    )

    st.metric(
        "Reporting Currency",
        REPORTING_CURRENCY,
    )

    st.caption(
        "Automatically detected "
        "from PayPal invoice data."
    )

    if (
        REPORTING_CURRENCY
        in ZERO_DECIMAL_CURRENCIES
    ):
        opening_balance = (
            st.number_input(
                (
                    "Opening Balance "
                    f"({REPORTING_CURRENCY})"
                ),
                min_value=0.0,
                value=float(
                    DEFAULT_OPENING_BALANCE
                ),
                step=1000.0,
                format="%.0f",
            )
        )

    else:
        opening_balance = (
            st.number_input(
                (
                    "Opening Balance "
                    f"({REPORTING_CURRENCY})"
                ),
                min_value=0.0,
                value=float(
                    DEFAULT_OPENING_BALANCE
                ),
                step=100.0,
                format="%.2f",
            )
        )

    st.divider()

    st.caption(
        "Mixed-currency forecasts "
        "are blocked until FX "
        "conversion is available."
    )


st.info(
    "Confirmed Forecast excludes "
    "DRAFT invoices. "
    "Scenario Forecast includes "
    "dated DRAFT invoices."
)

st.caption(
    "Reporting Currency: "
    f"**{REPORTING_CURRENCY}**"
)


# =========================================================
# Forecast calculations
# =========================================================

confirmed = {
    30: calculate_balance(
        events,
        30,
        opening_balance,
        REPORTING_CURRENCY,
        False,
    ),
    60: calculate_balance(
        events,
        60,
        opening_balance,
        REPORTING_CURRENCY,
        False,
    ),
    90: calculate_balance(
        events,
        90,
        opening_balance,
        REPORTING_CURRENCY,
        False,
    ),
}


scenario = {
    30: calculate_balance(
        events,
        30,
        opening_balance,
        REPORTING_CURRENCY,
        True,
    ),
    60: calculate_balance(
        events,
        60,
        opening_balance,
        REPORTING_CURRENCY,
        True,
    ),
    90: calculate_balance(
        events,
        90,
        opening_balance,
        REPORTING_CURRENCY,
        True,
    ),
}


baseline_scenario = {
    30: calculate_balance(
        raw_events,
        30,
        opening_balance,
        REPORTING_CURRENCY,
        True,
    ),
    60: calculate_balance(
        raw_events,
        60,
        opening_balance,
        REPORTING_CURRENCY,
        True,
    ),
    90: calculate_balance(
        raw_events,
        90,
        opening_balance,
        REPORTING_CURRENCY,
        True,
    ),
}


forecast_impact = {
    days:
    scenario[days]
    - baseline_scenario[days]

    for days in (
        30,
        60,
        90,
    )
}


needs_confirmation = [
    event
    for event in events
    if event.get(
        "needs_confirmation"
    )
]


human_confirmed = [
    event
    for event in events
    if event.get(
        "human_confirmed_due_date"
    )
]


draft_events = [
    event
    for event in events
    if (
        event.get("status")
        == "DRAFT"
    )
]


# =========================================================
# Executive Overview
# =========================================================

st.divider()

st.subheader(
    "Executive Overview"
)

m1, m2, m3, m4 = (
    st.columns(4)
)


m1.metric(
    "Opening Balance",
    money(
        opening_balance,
        REPORTING_CURRENCY,
    ),
)


m2.metric(
    "Confirmed 30D",
    money(
        confirmed[30],
        REPORTING_CURRENCY,
    ),
)


m3.metric(
    "Scenario 30D",
    money(
        scenario[30],
        REPORTING_CURRENCY,
    ),
)


scenario_delta = (
    scenario[30]
    - confirmed[30]
)


m4.metric(
    "Scenario Delta",
    money(
        scenario_delta,
        REPORTING_CURRENCY,
    ),
    delta=money_delta(
        scenario_delta,
        REPORTING_CURRENCY,
    ),
)


q1, q2, q3, q4 = (
    st.columns(4)
)


q1.metric(
    "PayPal Events",
    len(events),
)


q2.metric(
    "Draft Invoices",
    len(draft_events),
)


q3.metric(
    "Human Confirmed",
    len(human_confirmed),
)


q4.metric(
    "Pending Review",
    len(needs_confirmation),
)


# =========================================================
# Forecast Chart
# =========================================================

st.divider()

st.subheader(
    "30 / 60 / 90 Day Forecast"
)


forecast_rows = []

for days in (
    30,
    60,
    90,
):

    forecast_rows.append({
        "Horizon":
        f"{days} Days",

        "Series":
        "Confirmed",

        "Balance":
        confirmed[days],

        "Label":
        money(
            confirmed[days],
            REPORTING_CURRENCY,
        ),
    })

    forecast_rows.append({
        "Horizon":
        f"{days} Days",

        "Series":
        "Scenario",

        "Balance":
        scenario[days],

        "Label":
        money(
            scenario[days],
            REPORTING_CURRENCY,
        ),
    })


forecast_df = pd.DataFrame(
    forecast_rows
)


horizon_order = [
    "30 Days",
    "60 Days",
    "90 Days",
]


currency_axis_format = (
    ",.0f"
    if REPORTING_CURRENCY
    in ZERO_DECIMAL_CURRENCIES
    else ",.2f"
)


line_chart = (
    alt.Chart(
        forecast_df
    )
    .mark_line(
        strokeWidth=4,
    )
    .encode(
        x=alt.X(
            "Horizon:N",
            sort=horizon_order,
            title=None,
            axis=alt.Axis(
                labelAngle=0,
                labelPadding=12,
                labelFontSize=13,
            ),
        ),

        y=alt.Y(
            "Balance:Q",
            title=(
                "Cash Balance "
                f"({REPORTING_CURRENCY})"
            ),
            scale=alt.Scale(
                zero=False,
                padding=35,
            ),
            axis=alt.Axis(
                format=currency_axis_format,
                labelFontSize=12,
                titleFontSize=13,
            ),
        ),

        color=alt.Color(
            "Series:N",
            title=None,
            legend=alt.Legend(
                orient="top",
                labelFontSize=13,
                symbolSize=180,
            ),
        ),

        tooltip=[
            alt.Tooltip(
                "Horizon:N",
                title="Horizon",
            ),
            alt.Tooltip(
                "Series:N",
                title="Forecast",
            ),
            alt.Tooltip(
                "Balance:Q",
                title=REPORTING_CURRENCY,
                format=currency_axis_format,
            ),
        ],
    )
)


point_chart = (
    alt.Chart(
        forecast_df
    )
    .mark_circle(
        size=110,
    )
    .encode(
        x=alt.X(
            "Horizon:N",
            sort=horizon_order,
            axis=alt.Axis(
                labelAngle=0,
            ),
        ),

        y="Balance:Q",

        color=alt.Color(
            "Series:N",
            legend=None,
        ),

        tooltip=[
            alt.Tooltip(
                "Horizon:N",
                title="Horizon",
            ),
            alt.Tooltip(
                "Series:N",
                title="Forecast",
            ),
            alt.Tooltip(
                "Balance:Q",
                title=REPORTING_CURRENCY,
                format=currency_axis_format,
            ),
        ],
    )
)


label_chart = (
    alt.Chart(
        forecast_df
    )
    .mark_text(
        dy=-18,
        fontSize=14,
        fontWeight="bold",
        color="#FFFFFF",
    )
    .encode(
        x=alt.X(
            "Horizon:N",
            sort=horizon_order,
            axis=alt.Axis(
                labelAngle=0,
            ),
        ),

        y="Balance:Q",

        detail="Series:N",

        text="Label:N",
    )
)


forecast_chart = (
    line_chart
    + point_chart
    + label_chart
).properties(
    height=390
)


st.altair_chart(
    forecast_chart,
    width="stretch",
)


st.caption(
    "Confirmed = non-draft cash events. "
    "Scenario = Confirmed plus dated "
    "DRAFT events."
)


# =========================================================
# Forecast Table
# =========================================================

forecast_table = (
    pd.DataFrame({
        "Horizon": [
            "30 Days",
            "60 Days",
            "90 Days",
        ],

        "Confirmed": [
            money(
                confirmed[30],
                REPORTING_CURRENCY,
            ),
            money(
                confirmed[60],
                REPORTING_CURRENCY,
            ),
            money(
                confirmed[90],
                REPORTING_CURRENCY,
            ),
        ],

        "Scenario": [
            money(
                scenario[30],
                REPORTING_CURRENCY,
            ),
            money(
                scenario[60],
                REPORTING_CURRENCY,
            ),
            money(
                scenario[90],
                REPORTING_CURRENCY,
            ),
        ],

        "Scenario Delta": [
            money_delta(
                scenario[30]
                - confirmed[30],
                REPORTING_CURRENCY,
            ),
            money_delta(
                scenario[60]
                - confirmed[60],
                REPORTING_CURRENCY,
            ),
            money_delta(
                scenario[90]
                - confirmed[90],
                REPORTING_CURRENCY,
            ),
        ],
    })
)


st.dataframe(
    forecast_table,
    width="stretch",
    hide_index=True,
)


# =========================================================
# Human Confirmation Impact
# =========================================================

st.divider()

st.subheader(
    "Human Confirmation Impact"
)


has_impact = any(
    abs(value) > 0.000001
    for value
    in forecast_impact.values()
)


if has_impact:

    impact_columns = (
        st.columns(3)
    )

    for column, days in zip(
        impact_columns,
        (
            30,
            60,
            90,
        ),
    ):
        with column:

            st.metric(
                (
                    f"{days} Day "
                    "Forecast"
                ),

                money(
                    scenario[days],
                    REPORTING_CURRENCY,
                ),

                delta=money_delta(
                    forecast_impact[
                        days
                    ],
                    REPORTING_CURRENCY,
                ),
            )

            st.caption(
                "Before: "
                + money(
                    baseline_scenario[
                        days
                    ],
                    REPORTING_CURRENCY,
                )
                + " → After: "
                + money(
                    scenario[days],
                    REPORTING_CURRENCY,
                )
            )


    st.success(
        "Human-confirmed information "
        "changed the cash-flow forecast."
    )


else:

    st.info(
        "Human confirmations have not "
        "changed the current forecast."
    )


# =========================================================
# Human Review
# =========================================================

st.divider()

st.subheader(
    "Human Review"
)


if needs_confirmation:

    st.warning(
        f"{len(needs_confirmation)} "
        "event(s) require "
        "human confirmation."
    )


    for event in (
        needs_confirmation
    ):

        source_id = (
            event.get(
                "source_id"
            )
        )


        with st.expander(
            (
                "Review invoice "
                f"{source_id}"
            ),
            expanded=True,
        ):

            st.write(
                "**Amount:** "
                + money(
                    event_amount(
                        event
                    ),
                    event.get(
                        "currency"
                    )
                    or REPORTING_CURRENCY,
                )
            )


            st.write(
                "**Counterparty:** "
                f"{event.get('counterparty')}"
            )


            missing = (
                event.get(
                    "missing_fields",
                    [],
                )
            )


            st.write(
                "**Missing:** "
                + ", ".join(
                    missing
                )
            )


            if (
                "due_date"
                in missing
            ):

                confirmed_date = (
                    st.date_input(
                        "Expected due date",
                        value=None,
                        key=(
                            "due_date_"
                            f"{source_id}"
                        ),
                    )
                )


                if st.button(
                    "Confirm due date",
                    key=(
                        "confirm_"
                        f"{source_id}"
                    ),
                ):

                    if (
                        confirmed_date
                        is None
                    ):

                        st.warning(
                            "Please select "
                            "a due date."
                        )

                    else:

                        save_due_date_override(
                            source_id,
                            confirmed_date
                            .isoformat(),
                        )

                        st.session_state.pop(
                            "ai_review",
                            None,
                        )

                        st.rerun()


else:

    st.success(
        "No events require "
        "confirmation."
    )


# =========================================================
# Human Confirmed Values
# =========================================================

if human_confirmed:

    st.markdown(
        "### Human Confirmed Values"
    )


    for event in (
        human_confirmed
    ):

        source_id = (
            event.get(
                "source_id"
            )
        )


        current_date = (
            datetime.strptime(
                event["due_date"],
                "%Y-%m-%d",
            ).date()
        )


        with st.expander(
            (
                "✓ Human confirmed — "
                f"{source_id}"
            ),
            expanded=True,
        ):

            st.write(
                "**Amount:** "
                + money(
                    event_amount(
                        event
                    ),
                    event.get(
                        "currency"
                    )
                    or REPORTING_CURRENCY,
                )
            )


            st.write(
                "**Current due date:** "
                f"{event.get('due_date')}"
            )


            st.write(
                "**Source:** "
                "Human confirmation "
                "inside CashOps Agent"
            )


            edited_date = (
                st.date_input(
                    (
                        "Edit confirmed "
                        "due date"
                    ),
                    value=current_date,
                    key=(
                        "edit_"
                        f"{source_id}"
                    ),
                )
            )


            update_col, reset_col = (
                st.columns(2)
            )


            with update_col:

                if st.button(
                    "Update date",
                    key=(
                        "update_"
                        f"{source_id}"
                    ),
                ):

                    save_due_date_override(
                        source_id,
                        edited_date
                        .isoformat(),
                    )

                    st.session_state.pop(
                        "ai_review",
                        None,
                    )

                    st.rerun()


            with reset_col:

                if st.button(
                    "Reset confirmation",
                    key=(
                        "reset_"
                        f"{source_id}"
                    ),
                ):

                    remove_due_date_override(
                        source_id
                    )

                    st.session_state.pop(
                        "ai_review",
                        None,
                    )

                    st.rerun()


            st.caption(
                "Human-confirmed values "
                "are stored locally and "
                "are not written back "
                "to PayPal."
            )


# =========================================================
# AI Risk Review
# =========================================================

st.divider()

st.subheader(
    "🤖 AI Risk Review"
)


st.caption(
    "AI interprets the forecast "
    "and supporting evidence. "
    "Cash balances are calculated "
    "deterministically by CashOps Agent."
)


if st.button(
    "Run AI Risk Review",
    disabled=not bool(events),
):

    try:

        with st.spinner(
            "AI is reviewing "
            "cash-flow risk..."
        ):

            review = (
                run_ai_review(
                    events=events,
                    opening_balance=(
                        opening_balance
                    ),
                    confirmed_forecast=(
                        confirmed
                    ),
                    scenario_forecast=(
                        scenario
                    ),
                )
            )


            st.session_state[
                "ai_review"
            ] = review


    except Exception as e:

        st.error(
            "AI review failed: "
            f"{e}"
        )


review = (
    st.session_state.get(
        "ai_review"
    )
)


if review:

    risk_col, confidence_col = (
        st.columns(2)
    )


    risk_col.metric(
        "Cash Risk",
        review.get(
            "cash_risk",
            "unknown",
        ).upper(),
    )


    confidence_col.metric(
        "Data Confidence",
        review.get(
            "data_confidence",
            "unknown",
        ).upper(),
    )


    st.markdown(
        "### AI Summary"
    )


    st.write(
        review.get(
            "summary",
            "",
        )
    )


    st.markdown(
        "### Why this judgment?"
    )


    for item in review.get(
        "decision_basis",
        [],
    ):

        evidence_ids = (
            ", ".join(
                item.get(
                    "evidence_ids",
                    [],
                )
            )
        )


        st.markdown(
            "**"
            + evidence_ids
            + " — "
            + item.get(
                "finding",
                "",
            )
            + "**"
        )


        st.caption(
            item.get(
                "why_it_matters",
                "",
            )
        )


    st.markdown(
        "### Issues"
    )


    issues = review.get(
        "issues",
        [],
    )


    if issues:

        for item in issues:

            evidence_ids = (
                ", ".join(
                    item.get(
                        "evidence_ids",
                        [],
                    )
                )
            )


            st.warning(
                item.get(
                    "issue",
                    "",
                )
                + " ["
                + evidence_ids
                + "]"
            )


    else:

        st.success(
            "No material issues "
            "identified."
        )


    st.markdown(
        "### Questions for You"
    )


    questions = review.get(
        "questions_for_user",
        [],
    )


    if questions:

        for item in questions:

            evidence_ids = (
                ", ".join(
                    item.get(
                        "evidence_ids",
                        [],
                    )
                )
            )


            st.info(
                item.get(
                    "question",
                    "",
                )
                + " ["
                + evidence_ids
                + "]"
            )


    else:

        st.success(
            "No additional confirmation "
            "needed."
        )


    st.markdown(
        "### Recommended Actions"
    )


    actions = review.get(
        "recommended_actions",
        [],
    )


    if actions:

        for item in actions:

            evidence_ids = (
                ", ".join(
                    item.get(
                        "evidence_ids",
                        [],
                    )
                )
            )


            st.write(
                "• "
                + item.get(
                    "action",
                    "",
                )
                + " ["
                + evidence_ids
                + "]"
            )


    else:

        st.write(
            "No immediate actions "
            "recommended."
        )


    with st.expander(
        "View evidence used by AI"
    ):

        for item in review.get(
            "evidence",
            [],
        ):

            st.write(
                "**"
                + str(
                    item.get(
                        "id"
                    )
                )
                + "** — "
                + str(
                    item.get(
                        "fact"
                    )
                )
            )


    used_model = (
        review.get(
            "model_used"
        )
    )

    reporting_currency = (
        review.get(
            "reporting_currency"
        )
    )


    if used_model:
        st.caption(
            "AI Model Used: "
            f"**{used_model}**"
        )


    if reporting_currency:
        st.caption(
            "AI Reporting Currency: "
            f"**{reporting_currency}**"
        )


    st.caption(
        "Data Scope: This review "
        "is based on the current "
        "opening balance and loaded "
        "PayPal invoice data. Other "
        "expenses, bank transactions, "
        "payroll, taxes, or liabilities "
        "are not included unless provided."
    )


# =========================================================
# Source Data & Provenance
# =========================================================

st.divider()


with st.expander(
    "Source Data & Provenance"
):

    if events:

        rows = []


        for event in events:

            rows.append({
                "source":
                event.get(
                    "source"
                ),

                "invoice_id":
                event.get(
                    "source_id"
                ),

                "direction":
                event.get(
                    "direction"
                ),

                "amount":
                event_amount(
                    event
                ),

                "currency":
                event.get(
                    "currency"
                ),

                "status":
                event.get(
                    "status"
                ),

                "due_date":
                event.get(
                    "due_date"
                ),

                "due_date_source":
                (
                    event.get(
                        "due_date_source"
                    )
                    or "unknown"
                ),

                "counterparty":
                event.get(
                    "counterparty"
                ),

                "needs_confirmation":
                event.get(
                    "needs_confirmation"
                ),
            })


        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )


        st.caption(
            "PayPal remains the "
            "source record. "
            "Human-confirmed values "
            "are maintained as a "
            "separate local overlay."
        )


    else:

        st.info(
            "No source data available."
        )