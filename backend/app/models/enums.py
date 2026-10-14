from enum import StrEnum

SUPPORTED_CURRENCIES = ("USD", "EUR", "GBP", "CAD", "AUD", "CHF", "PLN", "UAH")


class ProjectStatus(StrEnum):
    active = "active"
    on_hold = "on_hold"
    completed = "completed"


class BillingType(StrEnum):
    hourly = "hourly"
    fixed = "fixed"
    non_billable = "non_billable"


class TaskStatus(StrEnum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskPriority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class TimeEntryStatus(StrEnum):
    running = "running"
    paused = "paused"
    stopped = "stopped"


class EntrySource(StrEnum):
    timer = "timer"
    manual = "manual"


class RateSource(StrEnum):
    project = "project"
    client = "client"
    user = "user"
    none = "none"


class InvoiceStatus(StrEnum):
    """Stored lifecycle. "overdue" and "partially paid" are derived (see services/invoices.py)."""

    draft = "draft"
    sent = "sent"
    paid = "paid"
    void = "void"


class InvoiceItemKind(StrEnum):
    time = "time"
    custom = "custom"


class PaymentMethod(StrEnum):
    bank_transfer = "bank_transfer"
    card = "card"
    cash = "cash"
    paypal = "paypal"
    other = "other"
