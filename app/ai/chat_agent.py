"""Chat agent: an LLM (OpenAI-compatible: OpenRouter / OpenAI / Azure) that can
call TOOLS to query and act on the app database, with per-user permissions.

The SAME agent is used by the HTTP endpoint (`POST /api/chat`) and the desktop
Chatbot tab, so a tool run always carries the caller's identity (CurrentUser) and
is authorized exactly like the REST endpoints:

    * Any authenticated user: view own profile / own watcher results, trigger a capture.
    * Admin only: list/soft-delete users, soft-delete executions, view any execution.
    * Denied actions return "You are a {role} and do not have permission to {thing}."
      which the model relays to the user (in English).
    * A request that no tool can serve (e.g. change password — no such tool exists)
      returns "I cannot perform this action because there is no tool to support it."

Tools operate through the writable Repository; the LLM never touches SQL directly.
Secrets and full prompts are never logged (only model + latency + request id).
"""

from __future__ import annotations

import json
import logging
import time

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

# Returned when the user asks for something that NO tool implements (feature not built).
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
    "Authorization is enforced by the tools themselves: if a tool returns an 'error' message, "
    "relay that exact message to the user verbatim and never claim you performed the action.\n"
    "If the user asks for an action that NONE of the available tools can perform (for example "
    "changing a password — there is no such tool), do not attempt any tool: reply with exactly "
    f"\"{NO_TOOL_MESSAGE}\"\n"
    "If the answer is not in the data, say so."
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
             max_context_chars: int | None = None) -> AIResponse:
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
            return self.opencode.run(prompt, snap, session_id=session_id,
                                     ctx_used=ctx_used)

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
        for m in (history or []):
            if m.role in ("user", "assistant") and m.content:
                messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": message})

        logger.info("chat START user=%s role=%s session=%s provider=%s model=%s ctx_used=%s",
                    user.username, user.role_name, session_id, provider, model, ctx_used)
        logger.info("chat USER message: %s", _short(message))

        start = time.monotonic()
        try:
            reply = self._run_loop(client, snap.model, user, messages)
        except Exception as e:
            return self._map_error(e, model, provider, session_id)
        latency = int((time.monotonic() - start) * 1000)
        logger.info("chat REPLY (%dms): %s", latency, _short(reply))
        return AIResponse.success(reply, model=model, provider=provider, session_id=session_id,
                                  execution_context_used=ctx_used, latency_ms=latency)

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

    def _run_loop(self, client, model: str, user: CurrentUser, messages: list[dict]) -> str:
        for step in range(1, MAX_TOOL_STEPS + 1):
            resp = client.chat.completions.create(
                model=model, messages=messages, tools=TOOLS,
                tool_choice="auto", temperature=0)
            choice = resp.choices[0].message
            if not choice.tool_calls:
                logger.info("chat step %d: model produced a final answer (no tool calls)", step)
                return (choice.content or "").strip()
            logger.info("chat step %d: model requested %d tool call(s)",
                        step, len(choice.tool_calls))
            messages.append({
                "role": "assistant", "content": choice.content,
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in choice.tool_calls],
            })
            for tc in choice.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("  TOOL CALL %s(%s) by user=%s",
                            tc.function.name, _short(json.dumps(args, ensure_ascii=False), 300),
                            user.username)
                result = self._dispatch(user, tc.function.name, args)
                logger.info("  TOOL RESULT %s -> %s", tc.function.name,
                            _short(json.dumps(result, ensure_ascii=False, default=str), 600))
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result, ensure_ascii=False, default=str)})
        logger.warning("chat hit MAX_TOOL_STEPS=%d without a final answer", MAX_TOOL_STEPS)
        return "I wasn't able to complete that request in a reasonable number of steps."

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
