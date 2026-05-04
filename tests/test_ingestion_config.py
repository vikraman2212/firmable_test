"""Unit tests for app.ingestion.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.config import (
    DEFAULT_SEED_CSV_PATH,
    DEFAULT_SYNC_PARQUET_PATH,
    DEFAULT_INDEX_NAME,
    load_ingestion_config,
)


class TestLoadIngestionConfig:
    def test_explicit_missing_path_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_ingestion_config(tmp_path / "missing.toml")

    def test_loads_opensearch_section(self, tmp_path):
        config_path = tmp_path / "ingestion.toml"
        config_path.write_text(
            """
[opensearch]
url = "http://search.internal:9200"
timeout = 15
""".strip(),
            encoding="utf-8",
        )

        cfg = load_ingestion_config(config_path)

        assert cfg.opensearch.url == "http://search.internal:9200"
        assert cfg.opensearch.timeout == 15

    def test_loads_seed_section(self, tmp_path):
        config_path = tmp_path / "ingestion.toml"
        config_path.write_text(
            """
[seed]
csv_path = "data/custom.csv"
index_name = "companies-custom"
batch_size = 250
row_limit = 123
""".strip(),
            encoding="utf-8",
        )

        cfg = load_ingestion_config(config_path)

        assert cfg.seed.csv_path == Path("data/custom.csv")
        assert cfg.seed.index_name == "companies-custom"
        assert cfg.seed.batch_size == 250
        assert cfg.seed.row_limit == 123

    def test_loads_sync_section(self, tmp_path):
        config_path = tmp_path / "ingestion.toml"
        config_path.write_text(
            """
[sync]
parquet_path = "data/staged/custom.parquet"
index_name = "companies-sync"
batch_size = 99
soft_delete = true
""".strip(),
            encoding="utf-8",
        )

        cfg = load_ingestion_config(config_path)

        assert cfg.sync.parquet_path == Path("data/staged/custom.parquet")
        assert cfg.sync.index_name == "companies-sync"
        assert cfg.sync.batch_size == 99
        assert cfg.sync.soft_delete is True

    def test_missing_sections_fall_back_to_defaults(self, tmp_path):
        config_path = tmp_path / "ingestion.toml"
        config_path.write_text("", encoding="utf-8")

        cfg = load_ingestion_config(config_path)

        assert cfg.seed.csv_path == DEFAULT_SEED_CSV_PATH
        assert cfg.seed.index_name == DEFAULT_INDEX_NAME
        assert cfg.sync.parquet_path == DEFAULT_SYNC_PARQUET_PATH
        assert cfg.sync.index_name == DEFAULT_INDEX_NAME
