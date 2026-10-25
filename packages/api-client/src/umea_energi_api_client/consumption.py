"""Meter points and consumption: which endpoint to call for which kind of contract.

The OpenAPI document says `GET /Contracts/{customerCode}` returns a single contract; the API
actually returns `{pager, groupedContracts: [{group, contracts: [...]}]}`. Which consumption
endpoint applies depends on the contract type, mirroring Umeå Energi's own Mina sidor.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from .errors import ApiError


class ContractType(StrEnum):
    ELECTRICITY = "ELECTRICITY"
    ELECTRICITY_GRID = "ELECTRICITY_GRID"
    DISTRICT_HEATING = "DISTRICT_HEATING"
    DISTRICT_COOLING = "DISTRICT_COOLING"
    BROADBAND = "BROADBAND"
    SOLAR_CELL = "SOLAR_CELL"


class Resolution(StrEnum):
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    HOUR = "HOUR"
    QUARTER = "QUARTER"
    """Quarter-hour values (15 minutes), where the meter reports them."""


ELECTRICITY_TYPES = frozenset({ContractType.ELECTRICITY, ContractType.ELECTRICITY_GRID})


@dataclass(frozen=True, kw_only=True)
class MeterPoint:
    contract_type: str
    """A `ContractType` value; kept as a string so unknown types still come through."""
    meter_point_no: str
    customer_code: str
    address: str | None
    contract_id: str | None


def parse_meter_points(data: Any, customer_code: str) -> list[MeterPoint]:
    """Meter points of the contracts in a `GET /Contracts/{customerCode}` response."""
    try:
        contracts: list[dict[str, Any]] = [
            contract
            for group in data.get("groupedContracts") or []
            for contract in group.get("contracts") or []
            if isinstance(contract, dict)
        ]
    except (AttributeError, TypeError) as error:
        raise ApiError(f"Unexpected contracts response: {error}") from error
    # Electricity supply contracts often have no meter point of their own; like Mina sidor, use
    # the grid contract's at the same address.
    grid_meter_points = {
        contract.get("address"): contract.get("meterPoint")
        for contract in contracts
        if contract.get("contractType") == ContractType.ELECTRICITY_GRID
    }
    meter_points: dict[tuple[str, str], MeterPoint] = {}
    for contract in contracts:
        # The document says contractType is an integer; the API sends names like "ELECTRICITY".
        contract_type = contract.get("contractType")
        address = contract.get("address")
        meter_point_no = contract.get("meterPoint")
        if not meter_point_no and contract_type == ContractType.ELECTRICITY:
            meter_point_no = grid_meter_points.get(address)
        if not contract_type or not meter_point_no:
            continue
        meter_points.setdefault(
            (str(contract_type), str(meter_point_no)),
            MeterPoint(
                contract_type=str(contract_type),
                meter_point_no=str(meter_point_no),
                customer_code=str(contract.get("customerId") or customer_code),
                address=address,
                contract_id=contract.get("contractId"),
            ),
        )
    return list(meter_points.values())


def midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)
