"""Chat agent: an LLM (OpenAI-compatible: OpenRouter / OpenAI / Azure) that can
call TOOLS to query and act on the app database, with per-user permissions.

The SAME agent is used by the HTTP endpoint (`POST /api/chat`) and the desktop
Chatbot tab, so a tool run always carries the caller's identity (CurrentUser) and
is authorized exactly like the REST endpoints:

    * Any authenticated user: view own profile / own watcher results, trigger a capture.
    * Admin only: list/soft-delete users, soft-delete executions, view any execution.
    * Denied actions return "You are a {role} and do not have permission to {thing}."
      which the model relays to the user (in English).
    * App requests with no tool to perform them (e.g. change password, edit rules) are
      NOT dead-ends: the model explains it can't do it directly and GUIDES the user to
      the right place (desktop tab or REST API). Off-topic questions are still refused.
      NO_TOOL_MESSAGE remains only as an internal fallback for an unknown tool name.

Tools operate through the writable Repository; the LLM never touches SQL directly.
Secrets and full prompts are never logged (only model + latency + request id).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.ai.api_auth import is_admin
from app.ai.models import (AIResponse, CONFIG_ERROR, PROVIDER_ERROR, RATE_LIMITED,
                           TIMEOUT, ChatMessage)
from app.ai.opencode_adapter import OpenCodeAdapter, compose_prompt
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService
from app.services.auth import CurrentUser, hash_password

logger = logging.getLogger("screen_watcher.ai.agent")


def _short(s, n: int = 600) -> str:
    """Truncate a value for logging (keeps logs readable, avoids dumping huge OCR/text)."""
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n} chars)"


MAX_TOOL_STEPS = 6

# Internal fallback only: returned by _dispatch when the model calls a tool name that
# doesn't exist. For real "no tool for this action" requests the model now GUIDES the
# user (see SUPPORT ROLE in SYSTEM_PROMPT) instead of returning this.
NO_TOOL_MESSAGE = "I cannot perform this action because there is no tool to support it."


def _deny(user: CurrentUser, thing: str) -> dict:
    """Permission-denied result naming the caller's role and the blocked action.

    The model is instructed to relay this text verbatim, e.g.
    "You are a viewer and do not have permission to delete a user account."
    """
    return {"error": f"You are a {user.role_name} and do not have permission to {thing}."}


# Refusal is ALWAYS in English, even when the user writes in Vietnamese.
OUT_OF_SCOPE_REPLY = (
    "This question is outside the scope of the Tool Watcher Assistant. "
    "Please ask about watcher results, OCR, rules, or system status."
)

SYSTEM_PROMPT = (
    "You are the assistant of Screen Watcher Pro, a desktop app that captures browser "
    "windows, runs OCR, evaluates alert rules and sends emails. Answer concisely, in the "
    "same language the user writes in (Vietnamese or English).\n"
    "SCOPE: you help people USE Tool Watcher. That includes friendly small talk and basic "
    "assistant duties — greetings, thanks, 'who are you?' / 'what can you do?' — plus anything "
    "about the app itself: watcher results, OCR text, alert rules, email notifications, "
    "executions, user accounts, system status, and how to operate the app. Be warm and helpful "
    "on these; for a greeting, greet back and briefly offer what you can do.\n"
    "Questions about the current status, issues, errors, alerts or operational health of "
    "'the system' / 'hệ thống' refer to Tool Watcher and ARE in scope — answer them from "
    "the watcher context and tools.\n"
    "IN-SCOPE examples (always answer): 'Hi' / 'Chào bạn', 'Bạn là ai?', 'Bạn giúp được gì?', "
    "'Issue hiện tại của hệ thống đang là gì?', 'Đánh giá hiện trạng vận hành', "
    "'Trạng thái watcher gần nhất?', 'Rule nào đang match?', 'What is the latest result?'.\n"
    "OUT-OF-SCOPE = topics unrelated to this app or general knowledge (cooking, repairing a "
    "motorbike, sports, weather, celebrities, poems, math homework, coding help unrelated to "
    "Tool Watcher, etc.). Examples (always refuse): 'Hướng dẫn sửa xe máy', 'Hướng dẫn nấu cơm', "
    "'Cách nấu thịt kho tàu?', 'Kết quả bóng đá?', 'Thời tiết hôm nay?', 'Viết giúp bài thơ'. "
    "ONLY for these truly-unrelated questions, do NOT answer and do NOT call any tool; reply "
    f"with exactly this sentence in English and nothing else: \"{OUT_OF_SCOPE_REPLY}\"\n"
    "When in doubt (e.g. a greeting or a vague question about the app), treat it as IN-SCOPE and help.\n"
    "Use the provided tools to look up or act on data (watcher results, executions, user "
    "accounts) whenever the question needs live data — do not invent values.\n"
    "Authorization is enforced by the tools themselves: if a tool returns an 'error' (e.g. "
    "permission denied), relay what it says to the user and never claim you performed the action.\n"
    "SUPPORT ROLE — help users solve Tool Watcher problems. If an app question or request has NO "
    "tool to perform it, do NOT just refuse: say you cannot do it directly, then GUIDE the user "
    "with concrete steps (in the desktop app or via the REST API). Reference:\n"
    "  - Change own password: forced on first login; otherwise POST /api/user/change-password; an "
    "admin resets it in the User Management tab or PUT /api/admin/users/{id}.\n"
    "  - Manage users (create / change role / enable-disable / delete): admin only — the User "
    "Management tab, or the /api/admin/users endpoints.\n"
    "  - Edit rules, alert recipients (owners), turn email on/off, sender/SMTP: edit "
    "config/rules.yaml (rules, owners.*.emails, email.enabled, email.from) and .smtp.env for the "
    "SMTP password, then restart the app; call get_alert_recipients to show who is configured now.\n"
    "  - Email not sent / who receives alerts: mail goes to the matched rule's owner_group "
    "recipients; check the 'Sent Emails' tab and the send explanation; a placeholder recipient or "
    "email.enabled=false means it won't really send.\n"
    "  - Run a capture: the Capture & OCR tab, or the trigger_capture tool / POST "
    "/api/watcher/executions.\n"
    "Keep guidance short and specific to Tool Watcher. Call a tool first whenever live data is "
    "needed. If the answer is not in the data, say so."
)

# ---- OpenAI-style tool schemas (permission is enforced at execution, not here) ----
TOOLS = [
    {"type": "function", "function": {
        "name": "get_my_profile",
        "description": "Get the current user's own account profile.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_latest_watcher_result",
        "description": "Latest watcher execution (OCR text, matched rules, email decisions). "
                       "A normal user sees only their own; an admin sees everyone's.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_alert_recipients",
        "description": "Who receives alert emails: the configured owner groups and their "
                       "recipient email addresses, which rule notifies which group, and "
                       "whether email sending is enabled (read from config/rules.yaml). Use "
                       "this for questions like 'which email receives alerts?' / "
                       "'email nhận alert là email nào?'.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_execution",
        "description": "Get one watcher execution (screenshot) by its execution_id.",
        "parameters": {"type": "object", "properties": {
            "execution_id": {"type": "string", "description": "Execution/screenshot UUID."}},
            "required": ["execution_id"]},
    }},
    {"type": "function", "function": {
        "name": "trigger_capture",
        "description": "Trigger a real capture+OCR+rule run for the given browser targets.",
        "parameters": {"type": "object", "properties": {
            "targets": {"type": "array", "items": {"type": "string", "enum": ["chrome", "edge"]},
                        "description": "Browsers to capture. Default both."},
            "launch": {"type": "boolean", "description": "Launch the browser if not open."}}},
    }},
    {"type": "function", "function": {
        "name": "generate_mock_data",
        "description": "Seed sample watcher executions into the DB for demo/testing so there is "
                       "data to query (admin only). Each creates a screenshot + OCR + matched "
                       "rule + notification. scenario: 'error' (ERROR/TIMEOUT → ops_team), "
                       "'payment' (declined/chargeback/fraud → finance_team), 'healthy' (no match).",
        "parameters": {"type": "object", "properties": {
            "count": {"type": "integer", "description": "How many to create (1-5, default 1)."},
            "scenario": {"type": "string", "enum": ["error", "payment", "healthy"],
                         "description": "Kind of mock result (default 'error')."}}},
    }},
    {"type": "function", "function": {
        "name": "delete_execution",
        "description": "Soft-delete a watcher execution by execution_id (admin only).",
        "parameters": {"type": "object", "properties": {
            "execution_id": {"type": "string"}}, "required": ["execution_id"]},
    }},
    {"type": "function", "function": {
        "name": "list_users",
        "description": "List all user accounts (admin only).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_user",
        "description": "Get a user account by username (admin only).",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"}}, "required": ["username"]},
    }},
    {"type": "function", "function": {
        "name": "create_user",
        "description": "Create a new user account (admin only). Ask the user for a password "
                       "if they did not provide one.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"},
            "password": {"type": "string", "description": "At least 6 characters."},
            "role": {"type": "string", "enum": ["admin", "operator", "viewer"],
                     "description": "Default viewer."},
            "full_name": {"type": "string"}, "email": {"type": "string"},
            "first_name": {"type": "string"}, "last_name": {"type": "string"},
            "phone": {"type": "string"}},
            "required": ["username", "password"]},
    }},
    {"type": "function", "function": {
        "name": "delete_user",
        "description": "Soft-delete a user account by username (admin only). Admin accounts "
                       "cannot be deleted.",
        "parameters": {"type": "object", "properties": {
            "username": {"type": "string"}}, "required": ["username"]},
    }},
]


class ChatAgent:
    def __init__(self, provider: ProviderConfig, repo, context_service: WatcherContextService,
                 capture_fn=None):
        """capture_fn(user_id, targets, launch) -> list[dict] enables the trigger tool."""
        self.cfg = provider
        self.repo = repo
        self.ctx = context_service
        self.capture_fn = capture_fn
        self.opencode = OpenCodeAdapter(provider)   # engine "opencode" (spec §11)
        self._roles = {r["id"]: r["name"] for r in repo.list_roles()}

    # ---------- public API ----------
    def chat(self, user: CurrentUser, message: str, session_id: str,
             history: list[ChatMessage] | None = None,
             include_context: bool = True,
             max_context_chars: int | None = None,
             on_event=None) -> AIResponse:
        """Run one chat turn (STREAMING under the hood) and return the full AIResponse.

        Pass `on_event(event)` to receive live events as they happen — a tuple
        (kind, payload) where kind is one of: 'meta', 'thinking', 'delta',
        'tool_call', 'tool_result', 'final', 'error'. The desktop Chatbot tab uses
        this to render the answer as it streams. The returned reply is always the
        COMPLETE final text (used for persistence)."""
        prep = self._prepare(user, message, session_id, history,
                             include_context, max_context_chars)
        if isinstance(prep, AIResponse):          # mock / opencode / config error
            if on_event and prep.reply:
                on_event(("delta", prep.reply))
                on_event(("final", prep.reply))
            return prep

        client, model, provider, ctx_used, messages = prep
        start = time.monotonic()
        final_text = ""
        try:
            for ev in self._iter_turn(client, model, user, messages):
                if on_event:
                    on_event(ev)
                if ev[0] == "final":
                    final_text = ev[1]
        except Exception as e:
            return self._map_error(e, model, provider, session_id)
        latency = int((time.monotonic() - start) * 1000)
        reply = (final_text or "").strip()
        logger.info("chat REPLY (%dms, %dch): %s", latency, len(reply), _short(reply))
        return AIResponse.success(reply, model=model, provider=provider, session_id=session_id,
                                  execution_context_used=ctx_used, latency_ms=latency)

    def chat_stream(self, user: CurrentUser, message: str, session_id: str,
                    history: list[ChatMessage] | None = None,
                    include_context: bool = True,
                    max_context_chars: int | None = None):
        """Generator variant for server-sent events (API `/api/chat` with stream=true).

        Yields (kind, payload) events; the caller accumulates 'delta' text and reads
        the terminal 'final' event for the complete reply (to persist)."""
        prep = self._prepare(user, message, session_id, history,
                             include_context, max_context_chars)
        if isinstance(prep, AIResponse):
            yield ("meta", {"model": prep.model, "provider": prep.provider,
                            "execution_context_used": prep.execution_context_used})
            if prep.ok:
                if prep.reply:
                    yield ("delta", prep.reply)
                yield ("final", prep.reply)
            else:
                yield ("error", {"error_code": prep.error_code, "message": prep.message})
                yield ("final", "")
            return

        client, model, provider, ctx_used, messages = prep
        yield ("meta", {"model": model, "provider": provider,
                        "execution_context_used": ctx_used})
        try:
            for ev in self._iter_turn(client, model, user, messages):
                yield ev
        except Exception as e:
            resp = self._map_error(e, model, provider, session_id)
            logger.warning("chat stream aborted: %s", type(e).__name__)
            yield ("error", {"error_code": resp.error_code, "message": resp.message})
            yield ("final", "")

    def _prepare(self, user: CurrentUser, message: str, session_id: str,
                 history, include_context: bool, max_context_chars):
        """Resolve config + watcher context, handle the mock/opencode/config-error
        short-circuits, and build the SDK message list.

        Returns an AIResponse to short-circuit the turn, or the tuple
        (client, model, provider, ctx_used, messages) for the streaming loop."""
        snap = self.cfg.resolve()          # dynamic: reads .env fresh (provider/model/key)
        provider, model = snap.provider, snap.model
        cap = max_context_chars or self.cfg.max_context_chars

        # Build the watcher-context block (scoped to the caller unless admin).
        ctx_block, ctx_used = "", False
        if include_context:
            scope = None if is_admin(user) else user.id
            wc = self.ctx.latest(scope)
            ctx_used = wc.has_data
            ctx_block = wc.to_prompt_block()[:cap]

        if self.cfg.mock:
            return AIResponse.success(
                "[MOCK mode] The assistant is running without a real LLM (ai.mock=true). "
                "Set ai.mock=false and configure the provider API key in .env to enable it.",
                model=model, provider=provider, session_id=session_id,
                execution_context_used=ctx_used, latency_ms=0)

        # Engine "opencode" (spec §11): one-shot prompt through the OpenCode CLI.
        # No DB tools on this path; the CLI manages its own provider keys, so the
        # snap.usable() key check below does not apply.
        if self.cfg.resolve_engine() == "opencode":
            prompt = compose_prompt(message, ctx_block, history)
            logger.info("chat START user=%s role=%s session=%s engine=opencode "
                        "provider=%s ctx_used=%s",
                        user.username, user.role_name, session_id, provider, ctx_used)
            logger.info("chat USER message: %s", _short(message))
            return self.opencode.run(prompt, snap, session_id=session_id, ctx_used=ctx_used)

        if not snap.usable():
            return AIResponse.failure(
                CONFIG_ERROR,
                f"API key {snap.key_env} is not set for provider '{provider}'. "
                "Add it to .env and try again.",
                model=model, provider=provider, session_id=session_id)

        try:
            client = self._build_client(snap)
        except Exception as e:
            return AIResponse.failure(CONFIG_ERROR, f"Provider setup failed: {e}",
                                      model=model, provider=provider, session_id=session_id)

        sys_text = SYSTEM_PROMPT
        sys_text += f"\n\nThe current user is '{user.username}' with role '{user.role_name}'."
        if ctx_block:
            sys_text += "\n\n=== LATEST WATCHER RESULT ===\n" + ctx_block
        messages = [{"role": "system", "content": sys_text}]
        n_hist = 0
        for m in (history or []):
            if m.role in ("user", "assistant") and m.content:
                messages.append({"role": m.role, "content": m.content})
                n_hist += 1
        messages.append({"role": "user", "content": message})

        logger.info("chat START user=%s role=%s session=%s provider=%s model=%s "
                    "engine=sdk stream=on ctx_used=%s history_msgs=%d",
                    user.username, user.role_name, session_id, provider, model,
                    ctx_used, n_hist)
        logger.info("chat USER message: %s", _short(message))
        if ctx_block:
            logger.info("chat CONTEXT injected: %d chars of watcher context", len(ctx_block))
        return (client, model, provider, ctx_used, messages)

    # ---------- LLM plumbing ----------
    def _build_client(self, snap):
        if snap.kind == "azure":
            from openai import AzureOpenAI
            return AzureOpenAI(api_key=snap.api_key, azure_endpoint=snap.base_url or "",
                               api_version=snap.api_version, timeout=self.cfg.timeout_seconds)
        from openai import OpenAI
        # A local server may not need a key; the SDK still requires a non-empty string.
        return OpenAI(api_key=snap.api_key or "not-required", base_url=snap.base_url,
                      timeout=self.cfg.timeout_seconds)

    def _iter_turn(self, client, model: str, user: CurrentUser, messages: list[dict]):
        """Streaming tool-calling loop. A generator yielding (kind, payload) events:
          ('thinking', text)  reasoning tokens (models that expose reasoning_content)
          ('delta', text)     answer tokens as they stream
          ('tool_call', {name, arguments})
          ('tool_result', {name, result})
          ('final', text)     the complete answer (terminal event)

        Every LLM step, tool call and tool result is logged for observability."""
        for step in range(1, MAX_TOOL_STEPS + 1):
            logger.info("chat step %d: requesting streamed completion (model=%s)", step, model)
            stream = client.chat.completions.create(
                model=model, messages=messages, tools=TOOLS,
                tool_choice="auto", temperature=0, stream=True)

            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_slots: dict[int, dict] = {}
            n_chunks = 0
            for chunk in stream:
                n_chunks += 1
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                # Some providers (DeepSeek/OpenRouter reasoning models) stream a
                # separate reasoning channel — surface it as "thinking".
                rc = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                if rc:
                    reasoning_parts.append(rc)
                    yield ("thinking", rc)
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                    yield ("delta", delta.content)
                for tcd in (getattr(delta, "tool_calls", None) or []):
                    slot = tool_slots.setdefault(tcd.index, {"id": None, "name": "", "args": ""})
                    if tcd.id:
                        slot["id"] = tcd.id
                    fn = getattr(tcd, "function", None)
                    if fn is not None:
                        if fn.name:
                            slot["name"] += fn.name
                        if fn.arguments:
                            slot["args"] += fn.arguments

            content = "".join(content_parts).strip()
            reasoning = "".join(reasoning_parts).strip()
            logger.info("chat step %d: %d stream chunk(s); content=%dch reasoning=%dch "
                        "tool_calls=%d", step, n_chunks, len(content), len(reasoning),
                        len(tool_slots))
            if reasoning:
                logger.info("chat step %d THINKING (reasoning): %s", step, _short(reasoning))

            if not tool_slots:
                logger.info("chat step %d: final answer, no tool calls (%dch)", step, len(content))
                yield ("final", content)
                return

            # The model wants to call tools; any content here is its narrative "thinking".
            if content:
                logger.info("chat step %d THINKING (content): %s", step, _short(content))
            ordered = [tool_slots[i] for i in sorted(tool_slots)]
            messages.append({
                "role": "assistant", "content": content or None,
                "tool_calls": [{"id": t["id"], "type": "function",
                                "function": {"name": t["name"], "arguments": t["args"]}}
                               for t in ordered],
            })
            # Parse + announce every tool call the model asked for in THIS step (the batch).
            batch = []
            for t in ordered:
                try:
                    args = json.loads(t["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                batch.append((t, args))
                logger.info("  TOOL CALL step=%d name=%s args=%s by user=%s",
                            step, t["name"],
                            _short(json.dumps(args, ensure_ascii=False), 300), user.username)
                yield ("tool_call", {"name": t["name"], "arguments": args})
            # Request batching for efficiency: run the step's tool calls CONCURRENTLY
            # (every DB access is guarded by db.lock, so this is thread-safe), then feed
            # all results back in ONE follow-up LLM call instead of one round-trip per tool.
            if len(batch) > 1:
                with ThreadPoolExecutor(max_workers=min(len(batch), 8)) as ex:
                    results = list(ex.map(
                        lambda pa: self._dispatch(user, pa[0]["name"], pa[1]), batch))
                logger.info("chat step %d: executed %d tool calls as a concurrent batch",
                            step, len(batch))
            else:
                results = [self._dispatch(user, batch[0][0]["name"], batch[0][1])]
            for (t, args), result in zip(batch, results):
                logger.info("  TOOL RESULT name=%s -> %s", t["name"],
                            _short(json.dumps(result, ensure_ascii=False, default=str), 600))
                yield ("tool_result", {"name": t["name"], "result": result})
                messages.append({"role": "tool", "tool_call_id": t["id"],
                                 "content": json.dumps(result, ensure_ascii=False, default=str)})
        logger.warning("chat hit MAX_TOOL_STEPS=%d without a final answer", MAX_TOOL_STEPS)
        yield ("final", "I wasn't able to complete that request in a reasonable number of steps.")

    def _map_error(self, e: Exception, model, provider, session_id) -> AIResponse:
        name = type(e).__name__
        if "Timeout" in name:
            code, msg = TIMEOUT, "The AI request timed out. Please try again."
        elif "RateLimit" in name:
            code, msg = RATE_LIMITED, "The AI provider is rate-limiting requests. Try again shortly."
        else:
            code, msg = PROVIDER_ERROR, "The AI provider returned an error."
        logger.warning("chat provider error: %s", name)
        return AIResponse.failure(code, msg, model=model, provider=provider, session_id=session_id)

    # ---------- tools (permission-enforced) ----------
    def _dispatch(self, user: CurrentUser, name: str, args: dict) -> dict:
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            return {"error": NO_TOOL_MESSAGE}
        try:
            return handler(user, **args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:  # never crash the loop on a tool failure
            logger.exception("tool %s failed", name)
            return {"error": f"Tool '{name}' failed: {e}"}

    def _user_public(self, row) -> dict:
        keys = row.keys()
        col = lambda k: (row[k] if k in keys else None)
        return {"id": row["id"], "username": row["username"], "full_name": row["full_name"],
                "email": col("email"), "role": self._roles.get(row["role_id"]),
                "is_active": bool(row["is_active"]), "deleted_at": col("deleted_at")}

    def _t_get_my_profile(self, user, **_):
        row = self.repo.get_user(user.id)
        return self._user_public(row) if row else {"error": "Account not found."}

    def _t_get_latest_watcher_result(self, user, **_):
        scope = None if is_admin(user) else user.id
        return self.ctx.latest(scope).to_dict()

    def _t_get_alert_recipients(self, user, **_):
        """Alert recipient configuration: owner groups + emails, which rule notifies
        which group, and whether email sending is on. Read fresh from config/rules.yaml
        so it reflects the current setup; contains no secrets (no SMTP password)."""
        from app import config
        cfg = config.load_app_config()
        email = cfg.get("email", {}) or {}
        owners = cfg.get("owners", {}) or {}
        groups = {name: list((g or {}).get("emails") or []) for name, g in owners.items()}
        rules = [{"rule": r.get("name") or r.get("id"),
                  "severity": r.get("severity"),
                  "owner_group": r.get("owner_group"),
                  "recipients": groups.get(r.get("owner_group"), [])}
                 for r in (cfg.get("rules") or [])]
        all_emails = sorted({e for lst in groups.values() for e in lst})
        return {
            "email_enabled": bool(email.get("enabled", False)),
            "email_from": email.get("from"),
            "owner_groups": groups,
            "rules": rules,
            "all_recipient_emails": all_emails,
        }

    def _t_get_execution(self, user, execution_id=None, **_):
        if not execution_id:
            return {"error": "execution_id is required."}
        wc = self.ctx.get(execution_id)
        if not wc.has_data:
            return {"error": "No execution with that id."}
        if not is_admin(user) and wc.owner_id != user.id:
            return _deny(user, "view another user's execution")
        return wc.to_dict(include_audit=True)

    def _t_trigger_capture(self, user, targets=None, launch=False, **_):
        if self.capture_fn is None:
            return {"error": "Capture is not available in this context."}
        targets = targets or ["chrome", "edge"]
        return {"results": self.capture_fn(user.id, targets, bool(launch))}

    def _t_generate_mock_data(self, user, count=1, scenario="error", **_):
        if not is_admin(user):
            return _deny(user, "generate mock data")
        from app.services.mock_data import MOCK_SCENARIOS, generate_mock_data
        scen = (scenario or "error").lower()
        if scen not in MOCK_SCENARIOS:
            return {"error": f"Unknown scenario '{scenario}'. "
                             f"Use one of: {', '.join(MOCK_SCENARIOS)}."}
        ids = generate_mock_data(self.repo, user.id, scen, count)
        self.repo.add_audit(user.id, "mock.generate", f"scenario={scen} count={len(ids)}")
        return {"created": len(ids), "scenario": scen, "execution_ids": ids}

    def _t_delete_execution(self, user, execution_id=None, **_):
        if not is_admin(user):
            return _deny(user, "delete a watcher execution")
        if not execution_id:
            return {"error": "execution_id is required."}
        n = self.repo.soft_delete_screenshot(execution_id)
        if n == 0:
            return {"error": "No live execution with that id."}
        self.repo.add_audit(user.id, "watcher.delete", f"chat soft-deleted {execution_id}")
        return {"status": "ok", "execution_id": execution_id, "soft_deleted": True}

    def _t_list_users(self, user, **_):
        if not is_admin(user):
            return _deny(user, "list user accounts")
        return {"users": [self._user_public(r) for r in self.repo.list_users()]}

    def _t_get_user(self, user, username=None, **_):
        if not is_admin(user):
            return _deny(user, "view user account details")
        row = self.repo.get_user_by_username((username or "").strip())
        return self._user_public(row) if row else {"error": f"No user '{username}'."}

    def _t_create_user(self, user, username=None, password=None, role="viewer",
                       full_name=None, email=None, first_name=None, last_name=None,
                       phone=None, **_):
        if not is_admin(user):
            return _deny(user, "create a user account")
        username = (username or "").strip()
        if len(username) < 3:
            return {"error": "Username must be at least 3 characters."}
        if not password or len(password) < 6:
            return {"error": "Password must be at least 6 characters."}
        if self.repo.get_user_by_username(username):
            return {"error": f"Username '{username}' already exists."}
        role_row = self.repo.get_role_by_name((role or "viewer").strip().lower())
        if role_row is None:
            return {"error": f"Invalid role '{role}'. Valid: admin, operator, viewer."}
        full = (full_name or " ".join(x for x in (first_name, last_name) if x) or "").strip()
        pwd_hash, salt = hash_password(password)
        uid = self.repo.create_user(username, pwd_hash, salt, full, role_row["id"],
                                    must_change_password=True, email=email,
                                    first_name=first_name, last_name=last_name, phone=phone)
        self.repo.add_audit(user.id, "user.create",
                            f"chat created {username} role={role_row['name']}")
        return {"status": "ok", "created": self._user_public(self.repo.get_user(uid))}

    def _t_delete_user(self, user, username=None, **_):
        if not is_admin(user):
            return _deny(user, "delete a user account")
        row = self.repo.get_user_by_username((username or "").strip())
        deleted = row is not None and "deleted_at" in row.keys() and row["deleted_at"]
        if row is None or deleted:
            return {"error": f"No live user '{username}'."}
        if self._roles.get(row["role_id"]) == "admin":
            return {"error": "You cannot delete admin account."}
        if row["id"] == user.id:
            return {"error": "You cannot delete your own account."}
        self.repo.soft_delete_user(row["id"])
        self.repo.add_audit(user.id, "user.delete", f"chat soft-deleted {username}")
        return {"status": "ok", "deleted_username": username, "soft_deleted": True}
