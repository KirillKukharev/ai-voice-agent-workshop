#!/usr/bin/env python3
"""
Apply OpenRouter LLM provider changes (config, security, openai adapter, yaml, .env.example).

Предварительно: sudo chown -R "$USER:$USER" <repo>  (если файлы root:root)

Usage:
  python3 scripts/apply-openrouter-provider.py .
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def print_preliminary() -> None:
    print(
        """
Предварительно:

1) Права на репозиторий (иначе правки не сохранятся)
     sudo chown -R "$USER:$USER" <каталог-Asterisk-AI-Voice-Agent>
   Проверка: touch src/config.py

2) Ключ OpenRouter в .env
     OPENROUTER_API_KEY=sk-or-v1-...
   Опционально: OPENROUTER_HTTP_REFERER, OPENROUTER_APP_TITLE

3) После скрипта: openrouter_llm.enabled: true, pipeline llm: openrouter_llm, перезапуск сервисов.
"""
    )


def main() -> int:
    if len(sys.argv) < 2:
        print_preliminary()
        print("Usage: python3 scripts/apply-openrouter-provider.py <repo_root>")
        return 1
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print("Not a directory:", root)
        return 1

    cfg = root / "src" / "config.py"
    sec = root / "src" / "config" / "security.py"
    oai = root / "src" / "pipelines" / "openai.py"
    yaml_path = root / "config" / "ai-agent.yaml"
    env_ex = root / ".env.example"

    for p in (cfg, sec, oai, yaml_path, env_ex):
        if not p.is_file():
            print("Missing:", p)
            return 1
        if not os.access(p, os.W_OK):
            print("Not writable — сначала chown:", p)
            return 1

    s = cfg.read_text(encoding="utf-8")
    needle = "    farewell_hangup_delay_sec: Optional[float] = None\n\n\nclass TelnyxLLMProviderConfig"
    insert = """    farewell_hangup_delay_sec: Optional[float] = None
    # Optional extra headers for OpenAI-compatible gateways (e.g. OpenRouter: HTTP-Referer, X-OpenRouter-Title).
    extra_http_headers: Optional[Dict[str, str]] = None


class TelnyxLLMProviderConfig"""
    if "extra_http_headers" not in s:
        if needle not in s:
            print("config.py: anchor not found; abort")
            return 1
        cfg.write_text(s.replace(needle, insert), encoding="utf-8")
        print("Patched", cfg)

    s = sec.read_text(encoding="utf-8")
    if "openrouter_key = os.getenv" not in s:
        doc_old = "    - TELNYX_API_KEY: Telnyx AI Inference API key (OpenAI-compatible LLM)\n    - AZURE_SPEECH_KEY:"
        doc_new = "    - TELNYX_API_KEY: Telnyx AI Inference API key (OpenAI-compatible LLM)\n    - OPENROUTER_API_KEY: OpenRouter (OpenAI-compatible chat completions at openrouter.ai)\n    - AZURE_SPEECH_KEY:"
        if doc_old not in s:
            print("security.py: docstring anchor not found; abort")
            return 1
        s = s.replace(doc_old, doc_new)
        telnyx_tail = """                if name_lower.startswith(("telnyx", "telenyx")) or chat_host == "api.telnyx.com":
                    provider_cfg["api_key"] = telnyx_key
                    providers_block[provider_name] = provider_cfg
        
        # Inject AZURE_SPEECH_KEY for Azure provider blocks (name-based or type-based)"""
        openrouter_inj = """                if name_lower.startswith(("telnyx", "telenyx")) or chat_host == "api.telnyx.com":
                    provider_cfg["api_key"] = telnyx_key
                    providers_block[provider_name] = provider_cfg

        # Inject OPENROUTER_API_KEY for openrouter* blocks or OpenRouter base URLs (type: openai)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            for provider_name, provider_cfg in list(providers_block.items()):
                if not isinstance(provider_cfg, dict):
                    continue
                name_lower = str(provider_name).lower()
                chat_host = _url_host(provider_cfg.get("chat_base_url", "") or provider_cfg.get("base_url", ""))
                if name_lower.startswith("openrouter") or chat_host == "openrouter.ai":
                    provider_cfg["api_key"] = openrouter_key
                    providers_block[provider_name] = provider_cfg
        
        # Inject AZURE_SPEECH_KEY for Azure provider blocks (name-based or type-based)"""
        if telnyx_tail not in s:
            print("security.py: injection anchor not found; abort")
            return 1
        s = s.replace(telnyx_tail, openrouter_inj)
        sec.write_text(s, encoding="utf-8")
        print("Patched", sec)

    s = oai.read_text(encoding="utf-8")
    changed = False
    hdr_old = """    if options.get("project"):
        headers["OpenAI-Project"] = options["project"]
    return headers"""
    hdr_new = """    if options.get("project"):
        headers["OpenAI-Project"] = options["project"]
    extra = options.get("extra_http_headers")
    if isinstance(extra, dict):
        for key, val in extra.items():
            if val is None:
                continue
            ev = str(val).strip()
            if ev:
                headers[str(key)] = ev
    return headers"""
    if hdr_old in s and "extra = options.get(\"extra_http_headers\")" not in s:
        s = s.replace(hdr_old, hdr_new)
        changed = True

    val_old = """        # If options contain an incompatible model, don't let it override validation.
        if "model" in options and "chat_model" not in options:
            if not str(options.get("model") or "").startswith(("gpt-", "o", "chatgpt")):
                merged.pop("model", None)
        return await super().validate_connectivity(merged)"""
    val_new = """        # If options contain an incompatible model, don't let it override validation — only for native OpenAI host.
        chat_host = _url_host(str(merged.get("chat_base_url") or ""))
        if chat_host == "api.openai.com" and "model" in options and "chat_model" not in options:
            if not str(options.get("model") or "").startswith(("gpt-", "o", "chatgpt")):
                merged.pop("model", None)
        return await super().validate_connectivity(merged)"""
    if val_old in s:
        s = s.replace(val_old, val_new)
        changed = True

    comp_old = """            "api_version": runtime_options.get(
                "api_version",
                self._pipeline_defaults.get("api_version", getattr(self._provider_defaults, "api_version", "ga")),
            ),
        }

        # If a pipeline swap left provider-specific LLM settings behind (e.g., Groq base_url + llama model),"""
    comp_new = """            "api_version": runtime_options.get(
                "api_version",
                self._pipeline_defaults.get("api_version", getattr(self._provider_defaults, "api_version", "ga")),
            ),
            "extra_http_headers": runtime_options.get(
                "extra_http_headers",
                self._pipeline_defaults.get(
                    "extra_http_headers",
                    getattr(self._provider_defaults, "extra_http_headers", None),
                ),
            ),
        }

        # If a pipeline swap left provider-specific LLM settings behind (e.g., Groq base_url + llama model),"""
    if '"extra_http_headers": runtime_options.get' not in s and comp_old in s:
        s = s.replace(comp_old, comp_new)
        changed = True

    if changed:
        oai.write_text(s, encoding="utf-8")
        print("Patched", oai)
    elif "extra = options.get(\"extra_http_headers\")" in s:
        print("openai.py: already patched")
    else:
        print("openai.py: anchors changed; patch manually")

    y = yaml_path.read_text(encoding="utf-8")
    if "openrouter_llm:" not in y:
        y_anchor = """    tools_enabled: false
    type: openai
  groq_stt:"""
        y_block = """    tools_enabled: false
    type: openai
  openrouter_llm:
    capabilities:
      - llm
    api_key: ${OPENROUTER_API_KEY}
    chat_base_url: https://openrouter.ai/api/v1
    chat_model: openai/gpt-4.1-nano
    enabled: false
    response_timeout_sec: 60
    temperature: 0.7
    type: openai
    extra_http_headers:
      HTTP-Referer: ${OPENROUTER_HTTP_REFERER:-}
      X-OpenRouter-Title: ${OPENROUTER_APP_TITLE:-Asterisk-AI-Voice-Agent}
  groq_stt:"""
        if y_anchor not in y:
            print("ai-agent.yaml: anchor not found; add openrouter_llm manually")
        else:
            yaml_path.write_text(y.replace(y_anchor, y_block), encoding="utf-8")
            print("Patched", yaml_path)

    e = env_ex.read_text(encoding="utf-8")
    if "OPENROUTER_API_KEY=" not in e:
        env_old = "MINIMAX_API_KEY=\n\n# Microsoft Azure Speech Service (STT & TTS)"
        env_new = """MINIMAX_API_KEY=

# OpenRouter LLM (OpenAI-compatible Chat Completions API)
# https://openrouter.ai/keys — models: https://openrouter.ai/models
OPENROUTER_API_KEY=
# Optional: site URL / app title for OpenRouter rankings (sent as HTTP headers)
# OPENROUTER_HTTP_REFERER=https://example.com
# OPENROUTER_APP_TITLE=Asterisk-AI-Voice-Agent

# Microsoft Azure Speech Service (STT & TTS)"""
        if env_old not in e:
            print(".env.example: anchor not found; add OPENROUTER_API_KEY manually")
        else:
            env_ex.write_text(e.replace(env_old, env_new), encoding="utf-8")
            print("Patched", env_ex)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
