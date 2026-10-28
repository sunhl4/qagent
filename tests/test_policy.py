from company_agent.policy import decide


def test_policy_is_fail_closed() -> None:
    assert decide("unknown", "lab", {}) == "deny"
    assert decide("company_capabilities", "unknown", {}) == "deny"


def test_policy_contract_cannot_disable_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "company_agent.policy.load_policy",
        lambda: {"fail_closed": False},
    )
    assert decide("company_capabilities", "lab", {}) == "deny"


def test_malformed_preset_contract_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "company_agent.policy.load_presets",
        lambda: {"presets": {"lab": {"visible_tools": "company_capabilities"}}},
    )
    assert decide("company_capabilities", "lab", {}) == "deny"


def test_policy_rejects_mismatched_device_identity(monkeypatch) -> None:
    from company_agent.catalog import load_policy

    bad = dict(load_policy())
    bad["device_provider"] = "other"
    monkeypatch.setattr("company_agent.policy.load_policy", lambda: bad)
    assert decide("quantum_device_run", "lab", {}) == "deny"


def test_policy_rejects_unknown_tools_even_when_preset_lists_them(monkeypatch) -> None:
    from company_agent.catalog import load_presets

    presets = load_presets()
    presets["presets"]["lab"]["visible_tools"].append("company_unknown")
    monkeypatch.setattr("company_agent.policy.load_presets", lambda: presets)
    assert decide("company_unknown", "lab", {}) == "deny"


def test_device_policy_requires_human() -> None:
    assert decide("quantum_device_run", "lab", {}) == "ask"
    assert decide("quantum_device_run", "sign", {}) == "ask"
    assert decide("quantum_device_run", "boot", {}) == "deny"
    assert decide("quantum_device_run", "algo", {}) == "deny"


def test_algorithm_development_cannot_see_device() -> None:
    assert decide("quantum_algorithm_catalog", "algo", {}) == "allow"
    assert decide("quantum_algorithm_run", "algo", {}) == "allow"
    assert decide("quantum_device_identity", "algo", {}) == "deny"


def test_algorithm_catalog_follows_lab_and_algo_visibility() -> None:
    assert decide("quantum_algorithm_catalog", "lab", {}) == "allow"
    assert decide("quantum_algorithm_catalog", "algo", {}) == "allow"
    assert decide("quantum_algorithm_catalog", "boot", {}) == "deny"
    assert decide("quantum_algorithm_catalog", "sign", {}) == "deny"
