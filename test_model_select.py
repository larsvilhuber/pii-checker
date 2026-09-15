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


def test_resolve_folder_returns_existing_dir(tmp_path):
    from interface import _resolve_folder
    assert _resolve_folder(str(tmp_path)) == str(tmp_path)


def test_resolve_folder_exits_on_non_dir(tmp_path):
    import pytest
    from interface import _resolve_folder
    with pytest.raises(SystemExit):
        _resolve_folder(str(tmp_path / "nope"))


def test_sha256_file_matches_hashlib(tmp_path):
    import hashlib
    from find_duplicities import sha256_file
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world" * 5000)  # spans several read chunks
    assert sha256_file(str(f)) == hashlib.sha256(f.read_bytes()).hexdigest()
    assert len(sha256_file(str(f))) == 64


def test_unload_ollama_model_posts_keep_alive_zero(monkeypatch):
    import requests
    import llm_client
    from llm_client import unload_ollama_model

    calls = []

    class _Resp:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(llm_client, "OLLAMA_ENDPOINTS", ["http://ollama.test:11434"])
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.append((url, kw)) or _Resp())

    assert unload_ollama_model("gemma4:e4b") is True
    (url, kw), = calls
    assert url == "http://ollama.test:11434/api/generate"
    assert kw["json"] == {"model": "gemma4:e4b", "keep_alive": 0}


def test_unload_ollama_model_returns_false_on_error(monkeypatch):
    import requests
    import llm_client
    from llm_client import unload_ollama_model

    def _boom(url, **kw):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(llm_client, "OLLAMA_ENDPOINTS", ["http://ollama.test:11434"])
    monkeypatch.setattr(requests, "post", _boom)
    assert unload_ollama_model("gemma4:e4b") is False
