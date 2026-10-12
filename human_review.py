import json
import os


OVERRIDES_FILE = "human_overrides.json"


def load_overrides():
    if not os.path.exists(OVERRIDES_FILE):
        return {}

    with open(OVERRIDES_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_overrides(overrides):
    with open(
        OVERRIDES_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            overrides,
            f,
            indent=2,
            ensure_ascii=False
        )


def save_due_date_override(source_id, due_date):
    overrides = load_overrides()

    overrides[source_id] = {
        "due_date": due_date
    }

    save_overrides(overrides)


def remove_due_date_override(source_id):
    overrides = load_overrides()

    if source_id in overrides:
        del overrides[source_id]

    save_overrides(overrides)


def apply_overrides(events):
    overrides = load_overrides()
    updated = []

    for event in events:
        item = dict(event)

        item["human_confirmed_due_date"] = False

        if item.get("due_date"):
            item["due_date_source"] = "paypal"
        else:
            item["due_date_source"] = None

        override = overrides.get(
            item.get("source_id")
        )

        # Human override is used only when PayPal
        # does not already provide a due date.
        if (
            override
            and override.get("due_date")
            and not item.get("due_date")
        ):
            item["due_date"] = override["due_date"]

            missing = [
                field
                for field in item.get(
                    "missing_fields", []
                )
                if field != "due_date"
            ]

            item["missing_fields"] = missing
            item["needs_confirmation"] = bool(missing)

            item["human_confirmed_due_date"] = True
            item["due_date_source"] = "human"

        updated.append(item)

    return updated