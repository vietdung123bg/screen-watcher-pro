"""Chat LLM provider config (FR04) — fully .env-driven and DYNAMIC.

Which provider/model/key is used is decided by environment variables and re-read
from .env on EVERY request, so you can switch provider or rotate keys live without
restarting the server or the app.

.env keys:
    PROVIDER=OPENROUTER            # OPENAI | AZURE_OPENAI | OPENROUTER | LOCAL

    OPENAI_API_KEY=...             OPENAI_MODEL=gpt-4o-mini
    AZURE_OPENAI_API_KEY=...       AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
                                   AZURE_OPENAI_MODEL=<deployment>  AZURE_OPENAI_API_VERSION=2024-06-01
    OPENROUTER_API_KEY=...         OPENROUTER_MODEL=openai/gpt-4o-mini
    LOCAL_LLM_ENDPOINT=http://localhost:11434/v1   LOCAL_LLM_MODEL=llama3.1   LOCAL_LLM_API_KEY=(optional)

Only non-secret knobs live in config/rules.yaml `ai:` (validated fail-fast at boot):
    ai:
      timeout_seconds: 120         # per-request timeout (spec: 120-180s)
      max_context_chars: 6000      # cap watcher context injected into the prompt
      mock: false                  # true -> skip the real API, return a canned reply
      provider: openrouter         # optional fallback if .env PROVIDER is unset
      engine: sdk                  # sdk (direct OpenAI-compatible SDK, with DB tools)
                                   # | opencode (spec §11: via the OpenCode CLI subprocess)

The engine can also be switched live with env CHAT_ENGINE=sdk|opencode (like PROVIDER).

ENDPOINT is only meaningful for AZURE_OPENAI (required) and LOCAL (base URL);
OPENAI/OPENROUTER use a fixed base URL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Canonical provider specs. kind: "openai" (base_url client) or "azure" (AzureOpenAI).
PROVIDERS: dict[str, dict] = {
    "openrouter": {"kind": "openai", "base_url": "https://openrouter.ai/api/v1",
                   "key_env": "OPENROUTER_API_KEY", "model_env": "OPENROUTER_MODEL",
                   "default_model": "openai/gpt-4o-mini"},
    "openai": {"kind": "openai", "base_url": None,
               "key_env": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL",
               "default_model": "gpt-4o-mini"},
    "azure_openai": {"kind": "azure",
                     "key_env": "AZURE_OPENAI_API_KEY", "endpoint_env": "AZURE_OPENAI_ENDPOINT",
                     "model_env": "AZURE_OPENAI_MODEL", "api_version_env": "AZURE_OPENAI_API_VERSION",
                     "default_api_version": "2024-06-01", "default_model": "gpt-4o-mini"},
    "local": {"kind": "openai", "base_url_env": "LOCAL_LLM_ENDPOINT",
              "base_url": "http://localhost:11434/v1", "key_env": "LOCAL_LLM_API_KEY",
              "model_env": "LOCAL_LLM_MODEL", "default_model": "llama3.1", "key_optional": True},
}

# Accept a few friendly spellings for the PROVIDER selector.
_ALIASES = {
    "azure": "azure_openai", "azureopenai": "azure_openai", "azure-openai": "azure_openai",
    "openai": "openai", "openrouter": "openrouter", "open-router": "openrouter",
    "local": "local", "local_llm": "local", "localllm": "local", "ollama": "local",
}

DEFAULT_TIMEOUT = 120
DEFAULT_MAX_CONTEXT_CHARS = 6000
DEFAULT_PROVIDER = "openrouter"
DEFAULT_ENGINE = "sdk"
VALID_ENGINES = ("sdk", "opencode")


class ProviderConfigError(ValueError):
    """Raised on invalid *structural* config (rules.yaml) so we fail fast at startup."""


def _reload_env() -> None:
    """Reload all env files (.chatbot.env etc.) so provider/key/model changes take
    effect without a restart."""
    try:
        from app import config
        config.load_env_files(override=True)
    except Exception:
        pass


def _normalize(name: str) -> str:
    return _ALIASES.get(name.strip().lower().replace(" ", ""), name.strip().lower())


@dataclass
class ResolvedProvider:
    """A concrete provider selection resolved from the current environment."""
    provider: str
    kind: str
    model: str
    api_key: str
    base_url: str | None
    api_version: str
    key_env: str
    key_optional: bool

    def usable(self) -> bool:
        return bool(self.api_key) or self.key_optional


@dataclass
class ProviderConfig:
    timeout_seconds: int
    max_context_chars: int
    mock: bool
    default_provider: str
    engine: str = DEFAULT_ENGINE

    @classmethod
    def from_app_config(cls, app_config: dict) -> "ProviderConfig":
        ai = (app_config or {}).get("ai", {}) or {}
        try:
            timeout_seconds = int(ai.get("timeout_seconds", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            raise ProviderConfigError("ai.timeout_seconds must be an integer.")
        if timeout_seconds <= 0:
            raise ProviderConfigError("ai.timeout_seconds must be > 0.")
        try:
            max_context_chars = int(ai.get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS))
        except (TypeError, ValueError):
            raise ProviderConfigError("ai.max_context_chars must be an integer.")
        if max_context_chars <= 0:
            raise ProviderConfigError("ai.max_context_chars must be > 0.")

        default_provider = _normalize(str(ai.get("provider", DEFAULT_PROVIDER)))
        if default_provider not in PROVIDERS:
            default_provider = DEFAULT_PROVIDER

        engine = str(ai.get("engine", DEFAULT_ENGINE)).strip().lower()
        if engine not in VALID_ENGINES:
            raise ProviderConfigError(
                f"ai.engine must be one of {', '.join(VALID_ENGINES)} (got '{engine}').")
        return cls(timeout_seconds=timeout_seconds, max_context_chars=max_context_chars,
                   mock=bool(ai.get("mock", False)), default_provider=default_provider,
                   engine=engine)

    # ---- dynamic resolution (reads .env fresh every call) ----
    def resolve(self) -> ResolvedProvider:
        _reload_env()
        name = _normalize(os.environ.get("PROVIDER", "") or self.default_provider)
        spec = PROVIDERS.get(name)
        if spec is None:
            name, spec = self.default_provider, PROVIDERS[self.default_provider]

        model = (os.environ.get(spec.get("model_env", ""), "").strip()
                 or spec.get("default_model", ""))
        if spec["kind"] == "azure":
            base_url = os.environ.get(spec["endpoint_env"], "").strip() or None
        elif "base_url_env" in spec:
            base_url = os.environ.get(spec["base_url_env"], "").strip() or spec.get("base_url")
        else:
            base_url = spec.get("base_url")
        api_version = (os.environ.get(spec.get("api_version_env", ""), "").strip()
                       or spec.get("default_api_version", ""))
        return ResolvedProvider(
            provider=name, kind=spec["kind"], model=model,
            api_key=os.environ.get(spec["key_env"], "").strip(), base_url=base_url,
            api_version=api_version, key_env=spec["key_env"],
            key_optional=bool(spec.get("key_optional", False)))

    def resolve_engine(self) -> str:
        """Which chat engine to use, resolved live: env CHAT_ENGINE wins over
        ai.engine from rules.yaml (invalid values fall back to the yaml one)."""
        env = os.environ.get("CHAT_ENGINE", "").strip().lower()
        return env if env in VALID_ENGINES else self.engine

    def safe_summary(self) -> str:
        """Loggable one-liner. NEVER includes the API key."""
        r = self.resolve()
        if self.mock:
            key_state = "mock"
        elif r.api_key:
            key_state = "set"
        elif r.key_optional:
            key_state = "not-required"
        else:
            key_state = "MISSING"
        return (f"engine={self.resolve_engine()} provider={r.provider} model={r.model} "
                f"timeout={self.timeout_seconds}s "
                f"max_ctx={self.max_context_chars} key[{r.key_env}]={key_state}")
