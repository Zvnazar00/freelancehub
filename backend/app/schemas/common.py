"""Shared schema building blocks."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, PlainSerializer, WithJsonSchema

from app.models.enums import SUPPORTED_CURRENCIES

Currency = Literal["USD", "EUR", "GBP", "CAD", "AUD", "CHF", "PLN", "UAH"]
assert set(Currency.__args__) == set(SUPPORTED_CURRENCIES)  # type: ignore[attr-defined]  # noqa: S101

_DECIMAL_RE = re.compile(r"^\d{1,12}(\.\d{1,2})?$")


def parse_money(value: Any) -> Decimal:
    """Money/rates must be JSON strings like "85.50" (ADR-09) — floats are rejected to avoid precision loss."""
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value.strip()):
        raise ValueError('must be a decimal string with up to 2 fraction digits, e.g. "85.50"')
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:  # pragma: no cover - regex already guarantees validity
        raise ValueError("invalid decimal") from exc


def _max(limit: Decimal) -> AfterValidator:
    def check(v: Decimal) -> Decimal:
        if v > limit:
            raise ValueError(f"must be at most {limit}")
        return v

    return AfterValidator(check)


_money_serializer = PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")
_money_schema = WithJsonSchema({"type": "string", "pattern": r"^\d{1,12}(\.\d{1,2})?$", "examples": ["85.00"]})

Rate = Annotated[Decimal, BeforeValidator(parse_money), _max(Decimal("99999999.99")), _money_serializer, _money_schema]
Amount = Annotated[
    Decimal, BeforeValidator(parse_money), _max(Decimal("999999999999.99")), _money_serializer, _money_schema
]
Hours = Annotated[Decimal, BeforeValidator(parse_money), _max(Decimal("999999.99")), _money_serializer, _money_schema]

_TIMEZONES = frozenset(available_timezones())

# Browsers and phones report time zones with CLDR/ICU identifiers, which keep some pre-rename IANA
# names (e.g. "Europe/Kiev"). Newer tzdata packages and PostgreSQL may ship only the current names,
# so legacy aliases are mapped to their current IANA name before validation and storage.
LEGACY_TIMEZONES: dict[str, str] = {
    "Europe/Kiev": "Europe/Kyiv",
    "Europe/Uzhgorod": "Europe/Kyiv",
    "Europe/Zaporozhye": "Europe/Kyiv",
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "America/Godthab": "America/Nuuk",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Catamarca": "America/Argentina/Catamarca",
    "America/Cordoba": "America/Argentina/Cordoba",
    "America/Jujuy": "America/Argentina/Jujuy",
    "America/Mendoza": "America/Argentina/Mendoza",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Louisville": "America/Kentucky/Louisville",
    "Pacific/Enderbury": "Pacific/Kanton",
    "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Truk": "Pacific/Chuuk",
}


def _check_timezone(value: str) -> str:
    value = LEGACY_TIMEZONES.get(value, value)
    if value not in _TIMEZONES:
        raise ValueError("unknown IANA time zone")
    return value


TimeZoneName = Annotated[str, AfterValidator(_check_timezone)]

HexColor = Annotated[str, AfterValidator(lambda v: _check_hex(v))]


def _check_hex(value: str) -> str:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise ValueError("must be a hex color like #8B7CFF")
    return value.upper()


class StrictModel(BaseModel):
    """Request bodies: unknown fields (e.g. user_id) are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: list[dict[str, Any]] | None = None
    context: dict[str, Any] | None = None
    request_id: str | None = None


class CurrencyAmount(ResponseModel):
    currency: str
    amount: Amount


def currency_amounts(amounts: dict[str, Decimal]) -> list[CurrencyAmount]:
    """Stable order: largest amount first, then currency code."""
    ordered = sorted(amounts.items(), key=lambda item: (-item[1], item[0]))
    return [CurrencyAmount(currency=c, amount=a) for c, a in ordered]


class Timestamped(ResponseModel):
    created_at: datetime
    updated_at: datetime
