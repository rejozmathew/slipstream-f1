import sys
from pathlib import Path

import uvicorn

import slipstream.api as api_module
import slipstream.cli as cli_module


def _run_serve(monkeypatch, tmp_path, *extra_args):
    requested_catalog_years = []
    monkeypatch.setattr(
        cli_module,
        "recent_seasons",
        lambda years: requested_catalog_years.append(years) or (2024, 2025, 2026),
    )
    monkeypatch.setattr(
        cli_module,
        "sync_catalog",
        lambda *_args, **_kwargs: {"sessions": [], "meetings": []},
    )
    monkeypatch.setattr(api_module, "create_app", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["slipstream", "serve", str(tmp_path), "--mode", "api-only", *extra_args],
    )

    cli_module.main()

    return requested_catalog_years


def test_serve_catalog_years_defaults_to_three(monkeypatch, tmp_path):
    monkeypatch.delenv("SLIPSTREAM_CATALOG_YEARS", raising=False)

    assert _run_serve(monkeypatch, tmp_path) == [3]


def test_explicit_catalog_years_overrides_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SLIPSTREAM_CATALOG_YEARS", "5")

    assert _run_serve(monkeypatch, tmp_path, "--catalog-years", "2") == [2]


def test_catalog_years_uses_environment_when_cli_is_omitted(monkeypatch, tmp_path):
    monkeypatch.setenv("SLIPSTREAM_CATALOG_YEARS", "4")

    assert _run_serve(monkeypatch, tmp_path) == [4]


def test_runtime_pirelli_history_horizon_uses_coordinator_default(
    monkeypatch, tmp_path
):
    constructor_kwargs = []
    recording = Path(__file__).parent / "fixtures" / "replays" / "sample-session.json"
    (tmp_path / "sample-session.json").write_bytes(recording.read_bytes())

    class Coordinator:
        def __init__(self, *_args, **kwargs):
            constructor_kwargs.append(kwargs)

    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    monkeypatch.setattr(api_module, "PirelliHistoricalCoordinator", Coordinator)

    api_module.create_app(tmp_path, public_live=False)

    assert constructor_kwargs == [{}]
