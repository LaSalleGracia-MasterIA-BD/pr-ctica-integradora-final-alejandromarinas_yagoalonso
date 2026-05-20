"""Unit tests of the triage rules (pure function, no Mongo, no FastAPI).

These tests cover RF-5 (rules) and the boundary cases CB-1..CB-4 from
specs/triage-pacientes.md. They run without any external dependency.

The rules are documented in design/triage-pacientes.md, table "Reglas
implementadas (RF-5)".
"""
from __future__ import annotations

import pytest

from src.api.triage import evaluate, get_rules_definition, RULES_VERSION


# -- Helpers ----------------------------------------------------------------


def _payload(**overrides) -> dict:
    """Default fully-normal payload. Tests override individual fields."""
    base = {
        "name": "Paciente Test",
        "gender": "M",
        "age": 40,
        "vital_signs": {
            "temperature_celsius": 36.8,
            "oxygen_saturation": 98,
            "heart_rate": 75,
            "respiratory_rate": 16,
            "systolic_bp": 120,
        },
        "symptoms": [],
        "risk_factors": [],
    }
    if "vital_signs" in overrides:
        base["vital_signs"] = {**base["vital_signs"], **overrides.pop("vital_signs")}
    base.update(overrides)
    return base


# -- TestGrave: 6 reglas individuales --------------------------------------


class TestGrave:
    def test_spo2_lt_92_is_grave(self):
        result = evaluate(_payload(vital_signs={"oxygen_saturation": 88}))
        assert result.level == "grave"
        assert "spo2_lt_92" in result.reasons

    def test_sbp_lt_90_is_grave(self):
        result = evaluate(_payload(vital_signs={"systolic_bp": 85}))
        assert result.level == "grave"
        assert "sbp_lt_90" in result.reasons

    def test_fr_gt_30_is_grave(self):
        result = evaluate(_payload(vital_signs={"respiratory_rate": 32}))
        assert result.level == "grave"
        assert "fr_gt_30" in result.reasons

    def test_fc_gt_130_is_grave(self):
        result = evaluate(_payload(vital_signs={"heart_rate": 145}))
        assert result.level == "grave"
        assert "fc_gt_130" in result.reasons

    def test_alteracion_conciencia_is_grave(self):
        result = evaluate(_payload(symptoms=["alteracion_conciencia"]))
        assert result.level == "grave"
        assert "alteracion_conciencia" in result.reasons

    def test_dolor_toracico_fuerte_is_grave(self):
        result = evaluate(_payload(symptoms=["dolor_toracico_fuerte"]))
        assert result.level == "grave"
        assert "dolor_toracico_fuerte" in result.reasons

    def test_multiple_grave_reasons_accumulate(self):
        result = evaluate(_payload(
            vital_signs={"oxygen_saturation": 85, "respiratory_rate": 35},
            symptoms=["alteracion_conciencia"],
        ))
        assert result.level == "grave"
        assert {"spo2_lt_92", "fr_gt_30", "alteracion_conciencia"}.issubset(
            set(result.reasons)
        )
        # score = numero de reglas disparadas (informativo)
        assert result.score >= 3


# -- TestMedio: reglas individuales -----------------------------------------


class TestMedio:
    def test_spo2_92_to_94_is_medio(self):
        for spo2 in [92, 93, 94]:
            result = evaluate(_payload(vital_signs={"oxygen_saturation": spo2}))
            assert result.level == "medio", f"spo2={spo2}"
            assert "spo2_92_94" in result.reasons

    def test_temp_ge_39_is_medio(self):
        result = evaluate(_payload(vital_signs={"temperature_celsius": 39.5}))
        assert result.level == "medio"
        assert "temp_ge_39" in result.reasons

    def test_fr_22_to_30_is_medio(self):
        result = evaluate(_payload(vital_signs={"respiratory_rate": 25}))
        assert result.level == "medio"
        assert "fr_22_30" in result.reasons

    def test_fc_110_to_130_is_medio(self):
        result = evaluate(_payload(vital_signs={"heart_rate": 120}))
        assert result.level == "medio"
        assert "fc_110_130" in result.reasons

    def test_anciano_con_fiebre_is_medio(self):
        result = evaluate(_payload(
            age=75,
            vital_signs={"temperature_celsius": 38.5},
        ))
        assert result.level == "medio"
        assert "anciano_riesgo_respiratorio" in result.reasons

    def test_anciano_con_sintoma_respiratorio_is_medio(self):
        result = evaluate(_payload(age=80, symptoms=["disnea"]))
        assert result.level == "medio"
        assert "anciano_riesgo_respiratorio" in result.reasons

    def test_no_anciano_con_fiebre_solo_no_dispara_anciano(self):
        # 65 anios + fiebre 38.5 NO dispara la regla de mayores (edad < 70)
        # y temperatura < 39 no dispara temp_ge_39. Resultado: leve.
        result = evaluate(_payload(
            age=65,
            vital_signs={"temperature_celsius": 38.5},
        ))
        assert result.level == "leve"


# -- TestLeve: caso por defecto + borders ----------------------------------


class TestLeve:
    def test_all_normal_is_leve(self):
        result = evaluate(_payload())
        assert result.level == "leve"
        assert result.score == 0

    def test_spo2_95_is_leve(self):
        result = evaluate(_payload(vital_signs={"oxygen_saturation": 95}))
        assert result.level == "leve"

    def test_unknown_symptom_does_not_trigger_rule(self):
        # CB-4: sintoma fuera del glosario activo se persiste pero no dispara reglas
        result = evaluate(_payload(symptoms=["dolor_de_cabeza_leve"]))
        assert result.level == "leve"

    def test_empty_symptoms_list_is_accepted(self):
        result = evaluate(_payload(symptoms=[]))
        assert result.level == "leve"


# -- TestBorders: CB-1 (limites estrictos de los umbrales) -----------------


class TestBorders:
    """CB-1 de la spec: documentar el comportamiento en las fronteras."""

    def test_spo2_91_is_grave(self):
        # 91 < 92 -> grave
        result = evaluate(_payload(vital_signs={"oxygen_saturation": 91}))
        assert result.level == "grave"

    def test_spo2_92_is_medio(self):
        # 92 in [92, 94] -> medio
        result = evaluate(_payload(vital_signs={"oxygen_saturation": 92}))
        assert result.level == "medio"

    def test_spo2_94_is_medio(self):
        result = evaluate(_payload(vital_signs={"oxygen_saturation": 94}))
        assert result.level == "medio"

    def test_spo2_95_is_leve(self):
        result = evaluate(_payload(vital_signs={"oxygen_saturation": 95}))
        assert result.level == "leve"

    def test_fr_30_is_not_grave(self):
        # fr > 30 estricto. 30 NO es grave (cae en fr_22_30 medio).
        result = evaluate(_payload(vital_signs={"respiratory_rate": 30}))
        assert result.level == "medio"
        assert "fr_22_30" in result.reasons

    def test_fr_31_is_grave(self):
        result = evaluate(_payload(vital_signs={"respiratory_rate": 31}))
        assert result.level == "grave"
        assert "fr_gt_30" in result.reasons

    def test_fc_130_is_not_grave(self):
        # fc > 130 estricto. 130 NO es grave (cae en fc_110_130 medio).
        result = evaluate(_payload(vital_signs={"heart_rate": 130}))
        assert result.level == "medio"
        assert "fc_110_130" in result.reasons

    def test_fc_131_is_grave(self):
        result = evaluate(_payload(vital_signs={"heart_rate": 131}))
        assert result.level == "grave"

    def test_sbp_89_is_grave(self):
        # sbp < 90 estricto.
        result = evaluate(_payload(vital_signs={"systolic_bp": 89}))
        assert result.level == "grave"

    def test_sbp_90_is_leve(self):
        result = evaluate(_payload(vital_signs={"systolic_bp": 90}))
        assert result.level == "leve"

    def test_temp_38_9_is_leve(self):
        # temp >= 39 estricto.
        result = evaluate(_payload(vital_signs={"temperature_celsius": 38.9}))
        assert result.level == "leve"

    def test_temp_39_is_medio(self):
        result = evaluate(_payload(vital_signs={"temperature_celsius": 39.0}))
        assert result.level == "medio"


# -- TestRulesDefinition: GET /rules ---------------------------------------


class TestRulesDefinition:
    def test_returns_version_and_levels(self):
        rules = get_rules_definition()
        assert rules["version"] == RULES_VERSION
        assert "levels" in rules
        assert set(rules["levels"].keys()) == {"grave", "medio"}

    def test_each_grave_rule_has_id_and_description(self):
        rules = get_rules_definition()
        for rule in rules["levels"]["grave"]:
            assert "id" in rule
            assert "description" in rule

    def test_rules_version_is_1_0(self):
        # Coherencia con spec RF-5 y design.
        assert RULES_VERSION == "1.0"


# -- TestGravePrecedence: si dispara grave y medio, gana grave -------------


def test_grave_takes_precedence_over_medio():
    """Si un payload cumple condiciones de grave y de medio, el nivel
    final es grave. La regla medio NO se anade a `reasons` (solo se
    listan reglas del nivel ganador)."""
    result = evaluate(_payload(
        vital_signs={
            "oxygen_saturation": 88,    # grave
            "temperature_celsius": 39.5, # medio (no se aplica)
        },
    ))
    assert result.level == "grave"
    assert "spo2_lt_92" in result.reasons
    assert "temp_ge_39" not in result.reasons
