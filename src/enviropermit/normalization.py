"""Unit normalization adapter for measured project scale parameters.

Converts equivalent physical/temporal units to canonical units without encoding
any statutory threshold values in Python.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math

from .contracts import NS, Contract, Measurement

_UNIT_FACTORS: dict[str, tuple[str, str, dict[str, Decimal]]] = {
    "production_capacity": (
        "ton/year",
        NS + "hasProductionCapacityTonPerYear",
        {
            "ton/year": Decimal("1"),
            "ton/tahun": Decimal("1"),
            "t/year": Decimal("1"),
            "t/tahun": Decimal("1"),
            "ton/yr": Decimal("1"),
            "kg/year": Decimal("0.001"),
            "kg/tahun": Decimal("0.001"),
            "kg/yr": Decimal("0.001"),
            "ton/month": Decimal("12"),
            "ton/bulan": Decimal("12"),
            "t/month": Decimal("12"),
            "t/bulan": Decimal("12"),
            "kg/month": Decimal("0.012"),
            "kg/bulan": Decimal("0.012"),
        },
    ),
    "wastewater_flow": (
        "m3/day",
        NS + "hasWastewaterFlowM3PerDay",
        {
            "m3/day": Decimal("1"),
            "m3/hari": Decimal("1"),
            "l/day": Decimal("0.001"),
            "l/hari": Decimal("0.001"),
            "liter/day": Decimal("0.001"),
            "liter/hari": Decimal("0.001"),
            "l/s": Decimal("86.4"),
            "liter/detik": Decimal("86.4"),
        },
    ),
    "land_area": (
        "ha",
        NS + "hasLandAreaHa",
        {
            "ha": Decimal("1"),
            "hektar": Decimal("1"),
            "hectare": Decimal("1"),
            "m2": Decimal("0.0001"),
            "sqm": Decimal("0.0001"),
        },
    ),
}


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." not in text:
        return text + ".0"
    return text


class NormalizedMeasurement(Contract):
    measurement_id: str
    subject_id: str
    scope_id: str
    metric: str
    raw_value: float
    raw_unit: str
    normalized_value: str | None = None
    canonical_unit: str | None = None
    predicate: str | None = None
    origin: str
    status: str
    issue: str | None = None


def normalize_measurement(measurement: Measurement) -> NormalizedMeasurement:
    metric_key = measurement.metric.strip().lower()
    unit_key = measurement.unit.strip().lower()

    if not math.isfinite(measurement.value) or measurement.value <= 0:
        return NormalizedMeasurement(
            measurement_id=measurement.id,
            subject_id=measurement.subject_id,
            scope_id=measurement.scope_id,
            metric=measurement.metric,
            raw_value=measurement.value,
            raw_unit=measurement.unit,
            origin=measurement.origin,
            status="REJECTED",
            issue=f"INVALID_MEASUREMENT_VALUE:{measurement.id}",
        )

    spec = _UNIT_FACTORS.get(metric_key)
    if spec is None:
        return NormalizedMeasurement(
            measurement_id=measurement.id,
            subject_id=measurement.subject_id,
            scope_id=measurement.scope_id,
            metric=measurement.metric,
            raw_value=measurement.value,
            raw_unit=measurement.unit,
            origin=measurement.origin,
            status="REJECTED",
            issue=f"UNSUPPORTED_METRIC:{measurement.id}:{measurement.metric}",
        )

    canonical_unit, predicate, factors = spec
    factor = factors.get(unit_key)
    if factor is None:
        return NormalizedMeasurement(
            measurement_id=measurement.id,
            subject_id=measurement.subject_id,
            scope_id=measurement.scope_id,
            metric=measurement.metric,
            raw_value=measurement.value,
            raw_unit=measurement.unit,
            canonical_unit=canonical_unit,
            origin=measurement.origin,
            status="REJECTED",
            issue=f"UNIT_MISMATCH:{measurement.id}:{measurement.unit}",
        )

    try:
        converted = Decimal(str(measurement.value)) * factor
    except InvalidOperation:
        return NormalizedMeasurement(
            measurement_id=measurement.id,
            subject_id=measurement.subject_id,
            scope_id=measurement.scope_id,
            metric=measurement.metric,
            raw_value=measurement.value,
            raw_unit=measurement.unit,
            canonical_unit=canonical_unit,
            origin=measurement.origin,
            status="REJECTED",
            issue=f"INVALID_MEASUREMENT_VALUE:{measurement.id}",
        )

    return NormalizedMeasurement(
        measurement_id=measurement.id,
        subject_id=measurement.subject_id,
        scope_id=measurement.scope_id,
        metric=measurement.metric,
        raw_value=measurement.value,
        raw_unit=measurement.unit,
        normalized_value=_format_decimal(converted),
        canonical_unit=canonical_unit,
        predicate=predicate,
        origin=measurement.origin,
        status="NORMALIZED",
    )
