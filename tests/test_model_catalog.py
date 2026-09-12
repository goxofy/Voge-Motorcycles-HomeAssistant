"""Tests for the observed VOGE business model catalog."""

import pytest

from custom_components.voge.model_catalog import (
    CATALOG_OBSERVED_ON,
    CATALOG_SOURCE,
    VEHICLE_MODELS,
    VogeVehicleModel,
    _build_model_index,
    match_vehicle_model,
)


def test_catalog_contains_all_18_observed_models() -> None:
    assert CATALOG_OBSERVED_ON == "2026-09-12"
    assert CATALOG_SOURCE == "booking_model_catalog"
    assert len(VEHICLE_MODELS) == 18
    assert len({model.model_code for model in VEHICLE_MODELS}) == 18


def test_cu250_automatic_variant_matches_catalog_family() -> None:
    model = match_vehicle_model("CU250 II代自动挡")
    assert model is not None
    assert model.model_name == "CU250Ⅱ代"
    assert model.model_code == "997"
    assert model.series == "CU"


def test_typography_and_case_are_normalized() -> None:
    assert match_vehicle_model("sr4 max").model_code == "958"  # type: ignore[union-attr]
    assert match_vehicle_model("SR250GT Ⅱ代").model_code == "999"  # type: ignore[union-attr]
    assert match_vehicle_model("CU525 链条版").model_code == "981"  # type: ignore[union-attr]


def test_unknown_model_does_not_fuzzy_match_or_use_product_id() -> None:
    assert match_vehicle_model("CU250 III代") is None
    assert match_vehicle_model(None, "Unknown motorcycle") is None
    assert match_vehicle_model("997") is None


def test_normalized_cross_model_alias_collision_is_rejected() -> None:
    models = (
        VogeVehicleModel("CU", "1", "CU Test", "100"),
        VogeVehicleModel("DS", "2", "DS Test", "200", ("cu-test",)),
    )

    with pytest.raises(ValueError, match="100 and 200"):
        _build_model_index(models)
