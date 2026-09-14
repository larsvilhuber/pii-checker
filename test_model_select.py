# test_model_select.py
# Tests for the interactive model-selection helpers (config.env rewrite and menu parsing).
# Run with: python -m pytest test_model_select.py

import builtins

from llm_client import save_model_to_config
from interface import _parse_model_choice


def test_save_model_rewrites_existing_line_and_keeps_rest(tmp_path):
    cfg = tmp_path / "config.env"
    cfg.write_text("LLM_PROVIDER=ollama\nLLM_MODEL=gemma4:e4b\n\n# ollama settings\nOLLAMA_ENDPOINTS=http://x:11434\n")
    save_model_to_config("llama3:8b", path=str(cfg))
    assert cfg.read_text() == "LLM_PROVIDER=ollama\nLLM_MODEL=llama3:8b\n\n# ollama settings\nOLLAMA_ENDPOINTS=http://x:11434\n"


def test_save_model_appends_when_line_missing(tmp_path):
    cfg = tmp_path / "config.env"
    cfg.write_text("LLM_PROVIDER=ollama\n")
    save_model_to_config("llama3:8b", path=str(cfg))
    assert cfg.read_text() == "LLM_PROVIDER=ollama\nLLM_MODEL=llama3:8b\n"


def test_parse_model_choice_accepts_number():
    assert _parse_model_choice("2", ["a", "b", "c"], current="a") == "b"


def test_parse_model_choice_accepts_name():
    assert _parse_model_choice("c", ["a", "b", "c"], current="a") == "c"


def test_parse_model_choice_empty_returns_current():
    assert _parse_model_choice("", ["a", "b"], current="b") == "b"


def test_parse_model_choice_empty_without_current_is_invalid():
    assert _parse_model_choice("", ["a", "b"], current=None) is None


def test_parse_model_choice_rejects_out_of_range_and_unknown():
    assert _parse_model_choice("9", ["a", "b"], current="a") is None
    assert _parse_model_choice("zzz", ["a", "b"], current="a") is None
