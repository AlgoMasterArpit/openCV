from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmissionFactor:
    kg_co2_per_unit: float
    unit: str
    source: str


# Water has no factor: pumping and treatment energy varies too much by city to state one honestly.
FACTORS: dict[str, EmissionFactor] = {
    "electricity": EmissionFactor(
        0.727,
        "kWh",
        "CEA CO2 Baseline Database v20.0, India grid weighted average FY 2023-24 "
        "(https://cea.nic.in/wp-content/uploads/2021/03/User_Guide_Version_20.0.pdf)",
    ),
    "gas": EmissionFactor(
        2.02,
        "SCM",
        "IPCC 2006 Vol. 2 Table 2.2, natural gas 56,100 kg CO2/TJ x ~36 MJ/SCM "
        "(https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_2_Ch2_Stationary_Combustion.pdf)",
    ),
}

UNIT_LABELS = {"electricity": "kWh", "gas": "SCM", "water": "kL"}


def co2_kg(meter_type: str, units: int | None) -> float | None:
    factor = FACTORS.get(meter_type)
    if factor is None or units is None:
        return None
    return round(units * factor.kg_co2_per_unit, 2)
