from copy import deepcopy

import pytest

from deeptutor.core.turn_request import TurnRequest
from deeptutor.services.model_selection import (
    LLMSelection,
    apply_llm_selection_to_catalog,
    list_llm_options,
)


def _catalog():
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "name": "OpenRouter",
                        "binding": "openrouter",
                        "base_url": "https://openrouter.ai/api/v1",
                        "api_key": "secret",
                        "api_version": "",
                        "extra_headers": {"x-secret": "nope"},
                        "models": [
                            {
                                "id": "m1",
                                "name": "Gemini Flash",
                                "model": "google/gemini-3-flash-preview",
                                "context_window": "1000000",
                                "reasoning_effort": "high",
                                "codex_supported_reasoning_levels": ["low", "high"],
                            },
                            {
                                "id": "m2",
                                "name": "GPT Mini",
                                "model": "openai/gpt-4o-mini",
                            },
                        ],
                    },
                    {
                        "id": "p2",
                        "name": "Local",
                        "binding": "ollama",
                        "base_url": "http://localhost:11434/v1",
                        "api_key": "",
                        "api_version": "",
                        "extra_headers": {},
                        "models": [{"id": "m3", "name": "Llama", "model": "llama3.2"}],
                    },
                ],
            },
            "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
        },
    }


def test_list_llm_options_is_redacted_and_marks_active_default():
    payload = list_llm_options(_catalog())
    assert payload["active"] == {"profile_id": "p1", "model_id": "m1"}
    assert [o["model_id"] for o in payload["options"]] == ["m1", "m2", "m3"]
    assert payload["options"][0]["is_active_default"] is True
    assert payload["options"][0]["context_window"] == 1000000
    assert payload["options"][0]["reasoning_effort"] == "high"
    assert payload["options"][0]["supported_reasoning_efforts"] == ["low", "high"]
    assert "api_key" not in payload["options"][0]
    assert "base_url" not in payload["options"][0]
    assert "extra_headers" not in payload["options"][0]


def test_apply_llm_selection_to_catalog_returns_copy_with_selected_active_ids():
    selected = apply_llm_selection_to_catalog(
        _catalog(), LLMSelection(profile_id="p2", model_id="m3")
    )
    assert selected["services"]["llm"]["active_profile_id"] == "p2"
    assert selected["services"]["llm"]["active_model_id"] == "m3"


def test_apply_llm_selection_does_not_mutate_source_catalog():
    catalog = _catalog()
    apply_llm_selection_to_catalog(catalog, LLMSelection(profile_id="p2", model_id="m3"))
    assert catalog["services"]["llm"]["active_profile_id"] == "p1"
    assert catalog["services"]["llm"]["active_model_id"] == "m1"


def test_apply_llm_selection_rejects_model_not_in_profile():
    try:
        apply_llm_selection_to_catalog(_catalog(), LLMSelection(profile_id="p2", model_id="m1"))
    except ValueError as exc:
        assert "Invalid LLM selection" in str(exc)
    else:
        raise AssertionError("expected invalid selection to fail")


def test_llm_selection_from_payload_accepts_valid_reasoning_effort():
    selection = LLMSelection.from_payload(
        {"profile_id": "p1", "model_id": "m1", "reasoning_effort": "High"}
    )
    assert selection.reasoning_effort == "high"


def test_llm_selection_from_payload_rejects_unsupported_reasoning_effort():
    try:
        LLMSelection.from_payload(
            {"profile_id": "p1", "model_id": "m1", "reasoning_effort": "unknown"}
        )
    except ValueError as exc:
        assert "reasoning_effort" in str(exc)
    else:
        raise AssertionError("expected invalid reasoning_effort to fail")


def test_llm_selection_from_payload_without_reasoning_effort_defaults_to_none():
    selection = LLMSelection.from_payload({"profile_id": "p1", "model_id": "m1"})
    assert selection.reasoning_effort is None


def test_llm_selection_to_dict_round_trips_reasoning_effort():
    selection = LLMSelection(profile_id="p1", model_id="m1", reasoning_effort="xhigh")
    payload = selection.to_dict()
    assert payload["reasoning_effort"] == "xhigh"
    restored = LLMSelection.from_payload(payload)
    assert restored == selection


def test_llm_selection_to_dict_omits_reasoning_effort_when_unset():
    selection = LLMSelection(profile_id="p1", model_id="m1")
    assert "reasoning_effort" not in selection.to_dict()


@pytest.mark.parametrize("effort", [None, "high", "ultra", "adaptive"])
def test_turn_request_preserves_conversation_reasoning_effort(effort):
    selection = {"profile_id": "p1", "model_id": "m1"}
    if effort is not None:
        selection["reasoning_effort"] = effort
    request = TurnRequest.model_validate({"content": "hello", "llm_selection": selection})
    assert request.to_payload()["llm_selection"] == selection


def test_selection_rejects_effort_not_supported_by_selected_model():
    with pytest.raises(ValueError, match="reasoning_effort"):
        apply_llm_selection_to_catalog(
            _catalog(),
            {"profile_id": "p1", "model_id": "m1", "reasoning_effort": "medium"},
        )


@pytest.mark.parametrize("effort", ["low", "high", "ultra", "adaptive"])
def test_declared_effort_is_scoped_and_does_not_mutate_model_default(effort):
    catalog = _catalog()
    model = catalog["services"]["llm"]["profiles"][0]["models"][0]
    model["codex_supported_reasoning_levels"] = ["low", "high", "ultra", "adaptive"]
    before = deepcopy(catalog)
    apply_llm_selection_to_catalog(
        catalog, {"profile_id": "p1", "model_id": "m1", "reasoning_effort": effort}
    )
    assert catalog == before


def test_options_include_reasoning_choices_for_custom_provider():
    catalog = _catalog()
    profile = catalog["services"]["llm"]["profiles"][1]
    profile["binding"] = "custom"
    profile["models"][0]["model"] = "a-reasoning-model"
    options = list_llm_options(catalog)["options"]
    assert options[2]["supported_reasoning_efforts"] == ["none", "low", "medium", "high"]


def test_declared_reasoning_choices_preserve_ultra():
    catalog = _catalog()
    model = catalog["services"]["llm"]["profiles"][0]["models"][0]
    model["codex_supported_reasoning_levels"] = ["low", "high", "ultra"]
    assert list_llm_options(catalog)["options"][0]["supported_reasoning_efforts"] == [
        "low",
        "high",
        "ultra",
    ]


def test_explicitly_non_reasoning_model_rejects_an_override():
    catalog = _catalog()
    catalog["services"]["llm"]["profiles"][1]["models"][0]["capabilities"] = {"reasoning": False}
    assert list_llm_options(catalog)["options"][2]["supported_reasoning_efforts"] == []
    with pytest.raises(ValueError, match="reasoning_effort"):
        apply_llm_selection_to_catalog(
            catalog, {"profile_id": "p2", "model_id": "m3", "reasoning_effort": "high"}
        )


def test_unknown_gateway_preserves_legacy_reasoning_override():
    catalog = _catalog()
    profile = catalog["services"]["llm"]["profiles"][1]
    profile["binding"] = "unknown_gateway"
    profile["models"][0]["model"] = "gpt-6.1-sol"
    assert list_llm_options(catalog)["options"][2]["supported_reasoning_efforts"] == []
    apply_llm_selection_to_catalog(
        catalog, {"profile_id": "p2", "model_id": "m3", "reasoning_effort": "xhigh"}
    )


def test_explicit_empty_reasoning_choices_reject_an_override():
    catalog = _catalog()
    catalog["services"]["llm"]["profiles"][1]["models"][0]["codex_supported_reasoning_levels"] = []
    with pytest.raises(ValueError, match="reasoning_effort"):
        apply_llm_selection_to_catalog(
            catalog, {"profile_id": "p2", "model_id": "m3", "reasoning_effort": "high"}
        )


def test_openrouter_keeps_gpt_model_reasoning_choices():
    catalog = _catalog()
    model = catalog["services"]["llm"]["profiles"][0]["models"][1]
    model["model"] = "openai/gpt-5.6-sol"
    options = list_llm_options(catalog)["options"]
    assert "xhigh" in options[1]["supported_reasoning_efforts"]
    apply_llm_selection_to_catalog(
        catalog, {"profile_id": "p1", "model_id": "m2", "reasoning_effort": "xhigh"}
    )
