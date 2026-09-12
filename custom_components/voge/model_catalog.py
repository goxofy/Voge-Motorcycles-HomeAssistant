"""Observed VOGE booking-business vehicle model catalog."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

CATALOG_OBSERVED_ON = "2026-09-12"
CATALOG_SOURCE = "booking_model_catalog"


@dataclass(frozen=True, slots=True)
class VogeVehicleModel:
    """One model observed in the authorized read-only booking catalog."""

    series: str
    tline_code: str
    model_name: str
    model_code: str
    aliases: tuple[str, ...] = ()


VEHICLE_MODELS: tuple[VogeVehicleModel, ...] = (
    VogeVehicleModel("CU", "906", "CU625", "907"),
    VogeVehicleModel("CU", "906", "CU250", "916"),
    VogeVehicleModel(
        "CU",
        "906",
        "CU525旅行版/2025款",
        "919",
        ("CU525旅行版", "CU525 旅行版", "CU525 2025款"),
    ),
    VogeVehicleModel("CU", "906", "CU525链条版", "981", ("CU525 链条版",)),
    VogeVehicleModel("CU", "906", "CU625自动挡", "992", ("CU625 自动挡",)),
    VogeVehicleModel("CU", "906", "CU530", "995"),
    VogeVehicleModel(
        "CU",
        "906",
        "CU250Ⅱ代",
        "997",
        ("CU250 II代", "CU250 Ⅱ代", "CU250 II代自动挡", "CU250 Ⅱ代 自动挡"),
    ),
    VogeVehicleModel("DS", "910", "DS900X 2025款", "928"),
    VogeVehicleModel("DS", "910", "DS625X", "956"),
    VogeVehicleModel("DS", "910", "DS500X", "985"),
    VogeVehicleModel("SR", "931", "SR250GT", "932"),
    VogeVehicleModel("SR", "931", "SR4 Max", "958", ("SR4 MAX",)),
    VogeVehicleModel(
        "SR",
        "931",
        "SR150C-PRO版",
        "973",
        ("SR150C PRO", "SR150C-PRO", "SR150C PRO版"),
    ),
    VogeVehicleModel("SR", "931", "SR150R", "988"),
    VogeVehicleModel(
        "SR",
        "931",
        "SR250GT II代",
        "999",
        ("SR250GT Ⅱ代", "SR250GTII代"),
    ),
    VogeVehicleModel("SR", "931", "SR450X", "1001"),
    VogeVehicleModel("RR", "934", "RR660S", "957"),
    VogeVehicleModel("RR", "934", "RR500S", "978"),
)


def _normalize_model_name(value: str) -> str:
    """Normalize harmless typography differences without fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def _build_model_index(
    models: tuple[VogeVehicleModel, ...],
) -> dict[str, VogeVehicleModel]:
    """Build an exact-name index and reject normalized cross-model collisions."""
    index: dict[str, VogeVehicleModel] = {}
    for model in models:
        for name in (model.model_name, *model.aliases):
            normalized = _normalize_model_name(name)
            if not normalized:
                raise ValueError("VOGE model catalog contains an empty normalized name")
            existing = index.get(normalized)
            if existing is not None and existing != model:
                raise ValueError(
                    "VOGE model catalog name collision between "
                    f"{existing.model_code} and {model.model_code}"
                )
            index[normalized] = model
    return index


_MODELS_BY_NAME = _build_model_index(VEHICLE_MODELS)


def match_vehicle_model(*names: str | None) -> VogeVehicleModel | None:
    """Match exact normalized server names to the observed business catalog."""
    for name in names:
        if not isinstance(name, str) or not name.strip():
            continue
        if model := _MODELS_BY_NAME.get(_normalize_model_name(name)):
            return model
    return None
