"""Provider config (D, FR04): switch between Llama and Azure OpenAI by editing
YAML only (config/rules.yaml -> `ai:` section). API keys come from environment
variables, never from YAML. Validated fail-fast at server startup.

    ai:
      provider: azure          # azure | llama
      model: gpt-4o-mini       # bare model name; prefix is added per provider
      working_dir: .           # safe cwd for the opencode subprocess
      timeout_seconds: 60
      mock: false              # true -> skip the real CLI, return a canned reply
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# provider -> (model prefix, env var holding the API key)
PROVIDERS: dict[str, tuple[str, str]] = {
    "azure": ("azure", "AZURE_OPENAI_API_KEY"),
    "llama": ("llama", "LLAMA_API_KEY"),
}


class ProviderConfigError(ValueError):
    """Raised on invalid config so the server can fail fast at startup."""


@dataclass
class ProviderConfig:
    provider: str
    model: str              # bare name, e.g. "gpt-4o-mini"
    model_full: str         # prefixed, e.g. "azure/gpt-4o-mini" (what opencode --model wants)
    api_key: str            # resolved from env; "" when mock
    env_var_name: str
    working_dir: str
    timeout_seconds: int
    mock: bool

    @classmethod
    def from_app_config(cls, app_config: dict) -> "ProviderConfig":
        """Build (and validate) from the parsed rules.yaml dict. Raises
        ProviderConfigError on any problem — call this at startup (fail fast)."""
        ai = (app_config or {}).get("ai", {}) or {}

        provider = str(ai.get("provider", "")).strip().lower()
        if provider not in PROVIDERS:
            raise ProviderConfigError(
                f"ai.provider must be one of {sorted(PROVIDERS)}, got {provider!r}."
            )

        model = str(ai.get("model", "")).strip()
        if not model:
            raise ProviderConfigError("ai.model must not be empty.")

        prefix, env_var = PROVIDERS[provider]
        # Allow the user to already include the prefix; don't double it.
        model_full = model if "/" in model else f"{prefix}/{model}"

        working_dir = str(ai.get("working_dir", ".")).strip() or "."
        if not os.path.isdir(working_dir):
            raise ProviderConfigError(
                f"ai.working_dir {working_dir!r} does not exist or is not a directory."
            )

        try:
            timeout_seconds = int(ai.get("timeout_seconds", 60))
        except (TypeError, ValueError):
            raise ProviderConfigError("ai.timeout_seconds must be an integer.")
        if timeout_seconds <= 0:
            raise ProviderConfigError("ai.timeout_seconds must be > 0.")

        mock = bool(ai.get("mock", False))

        api_key = os.environ.get(env_var, "").strip()
        if not mock and not api_key:
            raise ProviderConfigError(
                f"Provider {provider!r} needs env var {env_var} set "
                f"(or set ai.mock: true for demo/testing)."
            )

        return cls(
            provider=provider,
            model=model,
            model_full=model_full,
            api_key=api_key,
            env_var_name=env_var,
            working_dir=working_dir,
            timeout_seconds=timeout_seconds,
            mock=mock,
        )

    def safe_summary(self) -> str:
        """Loggable one-liner. NEVER includes the API key."""
        key_state = "mock" if self.mock else ("set" if self.api_key else "MISSING")
        return (f"provider={self.provider} model={self.model_full} "
                f"cwd={self.working_dir} timeout={self.timeout_seconds}s key={key_state}")
