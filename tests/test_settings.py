"""Unit tests for runtime settings helpers."""

from pathlib import Path

from app.settings import Settings


def test_effective_embedding_model_id_prefers_explicit_value(tmp_path):
    settings = Settings(
        embedding_model_id="explicit-model",
        embedding_model_state_file=str(tmp_path / "model_id"),
    )

    assert settings.effective_embedding_model_id == "explicit-model"


def test_effective_embedding_model_id_reads_state_file(tmp_path):
    state_file = tmp_path / "model_id"
    state_file.write_text("state-model\n", encoding="utf-8")

    settings = Settings(
        embedding_model_id="",
        embedding_model_state_file=str(state_file),
    )

    assert settings.effective_embedding_model_id == "state-model"


def test_effective_embedding_model_id_returns_empty_when_unconfigured(tmp_path):
    settings = Settings(
        embedding_model_id="",
        embedding_model_state_file=str(tmp_path / "missing-model-id"),
    )

    assert settings.effective_embedding_model_id == ""