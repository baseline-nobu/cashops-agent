import os
import json
import base64
import urllib.parse
import urllib.request


def load_env(path=".env.local"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key] = value


def paypal_get(url, token):
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


load_env()

base_url = os.environ["PAYPAL_BASE_URL"]
client_id = os.environ["PAYPAL_CLIENT_ID"]
client_secret = os.environ["PAYPAL_CLIENT_SECRET"]

credentials = base64.b64encode(
    f"{client_id}:{client_secret}".encode()
).decode()

token_request = urllib.request.Request(
    f"{base_url}/v1/oauth2/token",
    data=urllib.parse.urlencode(
        {"grant_type": "client_credentials"}
    ).encode(),
    headers={
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    method="POST",
)

with urllib.request.urlopen(token_request) as response:
    token_data = json.load(response)

access_token = token_data["access_token"]

invoice_list = paypal_get(
    f"{base_url}/v2/invoicing/invoices?page=1&page_size=10&total_required=true",
    access_token,
)

cashflow_events = []

for invoice in invoice_list.get("items", []):
    invoice_id = invoice.get("id")

    detail = paypal_get(
        f"{base_url}/v2/invoicing/invoices/{invoice_id}",
        access_token,
    )

    amount = detail.get("amount", {})
    invoice_detail = detail.get("detail", {})
    payment_term = invoice_detail.get("payment_term", {})

    recipients = detail.get("primary_recipients", [])
    counterparty = None

    if recipients:
        counterparty = (
            recipients[0]
            .get("billing_info", {})
            .get("email_address")
        )

    due_date = payment_term.get("due_date")

    missing_fields = []

    if not due_date:
        missing_fields.append("due_date")

    if not counterparty:
        missing_fields.append("counterparty")

    event = {
        "source": "paypal",
        "source_id": invoice_id,
        "type": "invoice_receivable",
        "direction": "inflow",
        "amount": amount.get("value"),
        "currency": amount.get("currency_code"),
        "counterparty": counterparty,
        "status": detail.get("status"),
        "due_date": due_date,
        "needs_confirmation": len(missing_fields) > 0,
        "missing_fields": missing_fields,
    }

    cashflow_events.append(event)

print(json.dumps(cashflow_events, indent=2, ensure_ascii=False))
