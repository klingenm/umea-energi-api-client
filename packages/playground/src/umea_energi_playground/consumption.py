"""The consumption page's data sources, and turning their responses into chartable rows."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from umea_energi_api_client import MeterPoint, Resolution, UmeaEnergiClient


@dataclass(frozen=True)
class Kind:
    label: str
    uses_resolution: bool = False
    uses_variables: bool = False


KINDS = {
    "consumption": Kind("Consumption", uses_resolution=True),
    "cost": Kind("Cost", uses_resolution=True),
    "readings": Kind("Meter readings"),
    "estimated": Kind("Statistics with estimated values (hour or day)", uses_resolution=True),
    "statistics": Kind("Meter statistics", uses_variables=True),
    "max": Kind("Max consumption (district heating)"),
}


async def fetch(
    api: UmeaEnergiClient,
    kind: str,
    access_token: str,
    point: MeterPoint,
    start: date,
    end: date,
    resolution: Resolution,
    variables: str,
) -> Any:
    match kind:
        case "cost":
            return await api.consumption_cost(access_token, point, start, end, resolution)
        case "readings":
            return await api.meter_readings(access_token, point, start, end)
        case "estimated":
            return await api.statistics_with_estimated_values(
                access_token, point, start, end, resolution
            )
        case "statistics":
            return await api.meter_statistics(access_token, point, start, end, variables or None)
        case "max":
            return await api.max_consumption(access_token, point, start, end)
        case _:
            return await api.consumption(access_token, point, start, end, resolution)


# Keys holding the period and the number to chart, in order of preference.
PERIOD_KEYS = ("period", "timeStamp", "date")
VALUE_KEYS = ("value", "consumption", "costIncl", "cost", "volume", "energy")


@dataclass(frozen=True)
class Row:
    period: str
    value: float
    share: float
    """`value` as a fraction of the largest value, for drawing a bar."""


def chart_rows(result: Any) -> list[Row]:
    """Period/value rows from a consumption or cost response, or [] if its shape is unknown."""
    items = result
    if isinstance(result, dict):
        items = next((value for value in result.values() if isinstance(value, list) and value), [])
    if not isinstance(items, list):
        return []
    points: list[tuple[str, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        period = next((item[key] for key in PERIOD_KEYS if item.get(key)), None)
        if period is None:
            continue
        value = next(
            (item[key] for key in VALUE_KEYS if isinstance(item.get(key), int | float)), None
        )
        if value is not None:
            points.append((str(period), float(value)))
    largest = max((abs(value) for _, value in points), default=0.0) or 1.0
    return [Row(period, value, abs(value) / largest) for period, value in points]
