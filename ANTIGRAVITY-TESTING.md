# ANTIGRAVITY AUTOMATED TESTING EVIDENCE

Tài liệu này ghi nhận kết quả chạy bộ kiểm thử tự động (automated testing) của dự án **Screen Watcher Pro** dựa trên các đặc tả thiết kế và kịch bản vận hành trong các tài liệu:
- [RUNBOOK-PRD22.md](file:///d:/AI/screen-watcher-pro/RUNBOOK-PRD22.md)
- [README.md](file:///d:/AI/screen-watcher-pro/README.md)
- [TESTING.md](file:///d:/AI/screen-watcher-pro/TESTING.md)

---

## 1. Thông tin môi trường chạy kiểm thử

- **Hệ điều hành:** Windows (win32)
- **Phiên bản Python:** 3.13.2
- **Phiên bản Pytest:** 9.1.1 (pluggy-1.6.0, anyio-4.14.1)
- **Thời gian chạy kiểm thử:** 2026-07-09T18:55:00+07:00 (Giờ địa phương)
- **Thư mục lưu trữ dữ liệu tạm thời cho test (Basetemp):** `d:\AI\screen-watcher-pro\tmp_test` (được cách ly trong không gian làm việc để tránh lỗi phân quyền hệ thống)

> [!NOTE]
> Tất cả các bài kiểm thử đều chạy ở chế độ **hoàn toàn offline**: không gọi LLM thật, sử dụng fake streaming client, fake CLI và database SQLite tạm thời (`tmp_path`).

---

## 2. Kết quả kiểm thử tổng quát

```text
======================= 106 passed, 1 warning in 47.51s =======================
```

Tất cả **106 test cases** đã được thực thi thành công mà không gặp bất kỳ lỗi nào.

---

## 3. Bản đồ đối chiếu các chức năng PRD 2.2 & Runbook với Test Cases

Bộ test kiểm thử chuyên sâu các yêu cầu cốt lõi được mô tả trong [RUNBOOK-PRD22.md](file:///d:/AI/screen-watcher-pro/RUNBOOK-PRD22.md) và thiết kế hệ thống trong [README.md](file:///d:/AI/screen-watcher-pro/README.md):

| Feature / Business Rule | File Test tương ứng | Các hàm Test chính | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :---: | :--- |
| **GR22-001**: AI Review không được phép tự ý kích hoạt (`ACTIVE`/`enabled=1`) Rule mới. | `tests/test_ai_review_governance.py` | `test_ai_cannot_create_active_rule`<br>`test_ai_cannot_create_enabled_rule`<br>`test_ai_cannot_set_status_active_on_existing_rule`<br>`test_ai_review_pipeline_never_activates` | **PASSED** | AI chỉ có thể đề xuất Draft Rule (`AI_SUGGESTED` / `enabled=0`). |
| **GR22-002**: Incident Rule bắt buộc phải do User/Admin tạo thủ công. | `tests/test_ai_review_governance.py`<br>`tests/test_prd22_routes.py` | `test_ai_review_pipeline_never_activates`<br>`test_operator_can_review_but_not_create_rules` | **PASSED** | Mọi rule do AI đề xuất không bao giờ được cấu hình là `is_incident_rule = 1`. |
| **GR22-003**: Khi Reject một Draft Rule từ AI đề xuất, hệ thống bắt buộc phải yêu cầu nhập lý do (`reject_reason`) và giữ lại rule trong DB. | `tests/test_ai_review_governance.py` | `test_reject_requires_reason`<br>`test_rejected_rule_is_kept_with_reason`<br>`test_user_reject_keeps_draft_with_reason_and_audits` | **PASSED** | Ràng buộc nghiệp vụ được kiểm thử cả ở tầng Service và kiểm tra lưu trữ DB thực tế kèm Audit Trail. |
| **Bước 1 & Bước 2 Runbook**: Incident Rule kích hoạt còi báo động console SOS và tính năng Acknowledge tắt còi. | `tests/test_prd22_routes.py`<br>`tests/test_event_service.py`<br>`tests/test_sos_watcher_job.py` | `test_evaluate_incident_rule_creates_sos`<br>`test_incident_rule_match_creates_sos_and_ack`<br>`test_job_alarms_and_marks_beeped`<br>`test_job_beep_uses_mock_not_sound` | **PASSED** | Kiểm thử luồng gửi sự kiện khớp Incident Rule tạo SOS Alert và tự động ghi nhận tiếng beep báo hiệu. |
| **Bước 3 & Bước 4 Runbook**: AI Review đề xuất Draft Rule cho text lạ và Admin thực hiện Approve để chuyển thành ACTIVE. | `tests/test_ai_review_governance.py`<br>`tests/test_prd22_routes.py` | `test_user_approve_activates_draft_and_confirms_event`<br>`test_ai_review_approve_flow` | **PASSED** | Đảm bảo luồng duyệt (Approve) từ Admin sẽ ACTIVE hóa rule và ghi nhận sự kiện chuyển trạng thái sang `CONFIRMED_ISSUE`. |
| **Bước 5 Runbook**: Reject Draft Rule bắt buộc lý do và lưu audit log. | `tests/test_ai_review_governance.py`<br>`tests/test_prd22_routes.py` | `test_user_reject_keeps_draft_with_reason_and_audits`<br>`test_ai_review_reject_requires_reason` | **PASSED** | Đảm bảo tính nhất quán của trạng thái `REJECTED`, ghi nhận lý do và kiểm chứng việc ghi nhận Audit Log. |
| **Issue Memory (Vectorstore)**: Tự động phát hiện lỗi mới (`new_issue`) và lỗi đã biết (`known_issue`) bằng SQLite local vector. | `tests/test_issue_memory_and_voice.py` | `test_issue_vectorstore_marks_first_event_new_then_repeated_event_known`<br>`test_chat_tool_get_known_issues_lists_vectorstore_records` | **PASSED** | Kiểm chứng cơ chế tính toán cosine similarity trên local SQLite vectorstore. |
| **Chatbot Scope Guardrail**: Từ chối chủ đề ngoài phạm vi ứng dụng bằng tiếng Anh cố định. | `tests/test_opencode_adapter.py` | `test_compose_prompt_has_scope_guardrail`<br>`test_out_of_scope_reply_is_english`<br>`test_sdk_system_prompt_has_scope_guardrail` | **PASSED** | Chatbot từ chối thân thiện các chủ đề không liên quan (như nấu ăn, sửa xe) bằng tiếng Anh tiêu chuẩn. |
| **Request Batching**: Gộp và chạy song song các tool calls trong cùng 1 bước LLM. | `tests/test_chat_agent_engine.py` | `test_sdk_batches_multiple_tool_calls_in_one_step` | **PASSED** | Tối ưu hóa số lượng round-trip tới LLM khi chatbot kích hoạt nhiều hàm cùng lúc. |
| **Database Migration**: Tự động chuyển đổi DB cũ sang schema UUIDv7 bảo mật và tối ưu. | `tests/test_migration_prd22.py` | `test_migration_creates_all_prd22_tables`<br>`test_migration_is_idempotent`<br>`test_migration_backs_up_db_once` | **PASSED** | Đảm bảo migration an toàn, idempotent và tự động tạo backup. |

---

## 4. Chi tiết các Test Suite đã thực hiện thành công

### `tests/test_ai_review_governance.py` (10 tests)
```text
tests/test_ai_review_governance.py::test_ai_cannot_create_active_rule PASSED
tests/test_ai_review_governance.py::test_ai_cannot_create_enabled_rule PASSED
tests/test_ai_review_governance.py::test_ai_cannot_set_status_active_on_existing_rule PASSED
tests/test_ai_review_governance.py::test_ai_draft_creation_can_be_disabled_by_config PASSED
tests/test_ai_review_governance.py::test_user_can_activate_rule PASSED
tests/test_ai_review_governance.py::test_reject_requires_reason PASSED
tests/test_ai_review_governance.py::test_rejected_rule_is_kept_with_reason PASSED
tests/test_ai_review_governance.py::test_user_approve_activates_draft_and_confirms_event PASSED
tests/test_ai_review_governance.py::test_user_reject_keeps_draft_with_reason_and_audits PASSED
tests/test_ai_review_governance.py::test_ai_review_pipeline_never_activates PASSED
```

### `tests/test_chat_agent_engine.py` (14 tests)
```text
tests/test_chat_agent_engine.py::test_engine_opencode_routes_through_cli PASSED
tests/test_chat_agent_engine.py::test_env_chat_engine_overrides_yaml PASSED
tests/test_chat_agent_engine.py::test_prompt_carries_watcher_context_and_question PASSED
tests/test_chat_agent_engine.py::test_mock_mode_bypasses_cli PASSED
tests/test_chat_agent_engine.py::test_cli_failure_maps_to_error_response PASSED
tests/test_chat_agent_engine.py::test_engine_default_is_sdk PASSED
tests/test_chat_agent_engine.py::test_engine_opencode_parsed PASSED
tests/test_chat_agent_engine.py::test_engine_invalid_raises PASSED
tests/test_chat_agent_engine.py::test_sdk_streaming_assembles_reply_and_forwards_events PASSED
tests/test_chat_agent_engine.py::test_sdk_streaming_single_round_no_tools PASSED
tests/test_chat_agent_engine.py::test_chat_stream_yields_ordered_events PASSED
tests/test_chat_agent_engine.py::test_sdk_batches_multiple_tool_calls_in_one_step PASSED
tests/test_chat_agent_engine.py::test_mock_chat_stream_emits_final PASSED
tests/test_chat_agent_engine.py::test_get_alert_recipients_reads_config PASSED
```

### `tests/test_chatbox_client.py` (11 tests)
```text
tests/test_chatbox_client.py::test_send_message_success PASSED
tests/test_chatbox_client.py::test_send_message_can_disable_context PASSED
tests/test_chatbox_client.py::test_send_message_shows_api_error_without_traceback PASSED
tests/test_chatbox_client.py::test_send_message_connection_error_is_friendly PASSED
tests/test_chatbox_client.py::test_send_message_timeout_is_friendly PASSED
tests/test_chatbox_client.py::test_send_message_401_hints_reauth PASSED
tests/test_chatbox_client.py::test_login_returns_token PASSED
tests/test_chatbox_client.py::test_login_failure_raises PASSED
tests/test_chatbox_client.py::test_notebook_flow_end_to_end PASSED
tests/test_chatbox_client.py::test_wrong_password_rejected PASSED
tests/test_chatbox_client.py::test_client_generated_uuid_session_accepted PASSED
```

### `tests/test_event_service.py` (7 tests)
```text
tests/test_event_service.py::test_create_event_from_screenshot_bridges_ocr PASSED
tests/test_event_service.py::test_normalize_builds_structured_fields PASSED
tests/test_event_service.py::test_evaluate_incident_rule_creates_sos PASSED
tests/test_event_service.py::test_evaluate_normal_db_rule_records_notification PASSED
tests/test_event_service.py::test_evaluate_no_match_triggers_ai_review PASSED
tests/test_event_service.py::test_evaluate_no_match_auto_review_disabled PASSED
tests/test_event_service.py::test_yaml_rules_synced_and_not_double_notified PASSED
```

### `tests/test_issue_memory_and_voice.py` (5 tests)
```text
tests/test_issue_memory_and_voice.py::test_issue_vectorstore_marks_first_event_new_then_repeated_event_known PASSED
tests/test_issue_memory_and_voice.py::test_watcher_context_exposes_issue_memory_status PASSED
tests/test_issue_memory_and_voice.py::test_chat_tool_get_known_issues_lists_vectorstore_records PASSED
tests/test_issue_memory_and_voice.py::test_voice_alert_falls_back_without_tts_command PASSED
tests/test_issue_memory_and_voice.py::test_explanation_shows_new_or_known_issue_memory PASSED
```

### `tests/test_jupyter_tab.py` (6 tests)
```text
tests/test_jupyter_tab.py::test_build_command_uses_no_browser_and_binds_host_port PASSED
tests/test_jupyter_tab.py::test_notebook_url_preserves_token_and_targets_the_notebook PASSED
tests/test_jupyter_tab.py::test_notebook_url_without_token PASSED
tests/test_jupyter_tab.py::test_notebook_url_preserves_localhost_host_and_port PASSED
tests/test_jupyter_tab.py::test_build_webview_command_targets_the_child_module PASSED
tests/test_jupyter_tab.py::test_webview_child_module_imports_without_pywebview PASSED
```

### `tests/test_migration_prd22.py` (5 tests)
```text
tests/test_migration_prd22.py::test_migration_creates_all_prd22_tables PASSED
tests/test_migration_prd22.py::test_migration_is_idempotent PASSED
tests/test_migration_prd22.py::test_migration_backs_up_db_once PASSED
tests/test_migration_prd22.py::test_migration_survives_existing_legacy_db PASSED
tests/test_migration_prd22.py::test_indexes_created PASSED
```

### `tests/test_mock_data.py` (4 tests)
```text
tests/test_mock_data.py::test_seed_first_run_is_idempotent PASSED
tests/test_mock_data.py::test_seed_first_run_latest_is_a_matched_execution PASSED
tests/test_mock_data.py::test_generate_mock_data_clamps_count_and_falls_back_scenario PASSED
tests/test_mock_data.py::test_chat_tool_generate_mock_data_admin_only PASSED
```

### `tests/test_opencode_adapter.py` (23 tests)
```text
tests/test_opencode_adapter.py::test_compose_prompt_has_all_sections PASSED
tests/test_opencode_adapter.py::test_compose_prompt_has_scope_guardrail PASSED
tests/test_opencode_adapter.py::test_compose_prompt_guides_app_problems_without_a_tool PASSED
tests/test_opencode_adapter.py::test_out_of_scope_reply_is_english PASSED
tests/test_opencode_adapter.py::test_sdk_system_prompt_has_scope_guardrail PASSED
tests/test_opencode_adapter.py::test_sdk_system_prompt_guides_when_no_tool PASSED
tests/test_opencode_adapter.py::test_compose_prompt_without_context PASSED
tests/test_opencode_adapter.py::test_compose_prompt_includes_recent_history_only PASSED
tests/test_opencode_adapter.py::test_model_mapping[azure_openai-gpt-4o-mini-azure/gpt-4o-mini] PASSED
tests/test_opencode_adapter.py::test_model_mapping[openai-gpt-4o-mini-openai/gpt-4o-mini] PASSED
tests/test_opencode_adapter.py::test_model_mapping[openrouter-openai/gpt-4o-mini-openrouter/openai/gpt-4o-mini] PASSED
tests/test_opencode_adapter.py::test_model_mapping[local-llama3.1-ollama/llama3.1] PASSED
tests/test_opencode_adapter.py::test_model_env_override_wins PASSED
tests/test_opencode_adapter.py::test_run_success PASSED
tests/test_opencode_adapter.py::test_run_passes_prompt_via_stdin PASSED
tests/test_opencode_adapter.py::test_run_nonzero_exit_is_provider_error PASSED
tests/test_opencode_adapter.py::test_run_empty_stdout_is_provider_error PASSED
tests/test_opencode_adapter.py::test_run_timeout PASSED
tests/test_opencode_adapter.py::test_missing_binary_is_config_error PASSED
tests/test_opencode_adapter.py::test_not_installed_is_config_error PASSED
tests/test_opencode_adapter.py::test_arg_prompt_mode_builds_spec_command PASSED
tests/test_opencode_adapter.py::test_stdin_mode_omits_prompt_from_argv PASSED
tests/test_opencode_adapter.py::test_ansi_codes_are_stripped PASSED
```

### `tests/test_prd22_routes.py` (8 tests)
```text
tests/test_prd22_routes.py::test_events_require_auth PASSED
tests/test_prd22_routes.py::test_viewer_cannot_manage_rules_but_can_read PASSED
tests/test_prd22_routes.py::test_operator_can_review_but_not_create_rules PASSED
tests/test_prd22_routes.py::test_incident_rule_match_creates_sos_and_ack PASSED
tests/test_prd22_routes.py::test_ai_review_approve_flow PASSED
tests/test_prd22_routes.py::test_ai_review_reject_requires_reason PASSED
tests/test_prd22_routes.py::test_rule_enable_disable_and_audit PASSED
tests/test_prd22_routes.py::test_event_pagination_and_filters PASSED
```

### `tests/test_rich_text.py` (5 tests)
```text
tests/test_rich_text.py::test_html_inline_to_markdown PASSED
tests/test_rich_text.py::test_html_plain_text_passthrough PASSED
tests/test_rich_text.py::test_html_list_becomes_markdown_bullets PASSED
tests/test_rich_text.py::test_insert_markdown_strips_syntax_and_applies_tags PASSED
tests/test_rich_text.py::test_insert_markdown_keeps_underscored_identifiers_literal PASSED
```

### `tests/test_rule_engine_metadata.py` (3 tests)
```text
tests/test_rule_engine_metadata.py::test_evaluate_rule_preserves_metadata_without_affecting_match PASSED
tests/test_rule_engine_metadata.py::test_evaluate_rule_defaults_metadata_to_empty_dict PASSED
tests/test_rule_engine_metadata.py::test_load_app_config_preserves_rule_metadata PASSED
```

### `tests/test_sos_watcher_job.py` (5 tests)
```text
tests/test_sos_watcher_job.py::test_job_alarms_and_marks_beeped PASSED
tests/test_sos_watcher_job.py::test_job_beep_uses_mock_not_sound PASSED
tests/test_sos_watcher_job.py::test_job_graceful_stop PASSED
tests/test_sos_watcher_job.py::test_job_disabled_never_polls PASSED
tests/test_sos_watcher_job.py::test_repo_cooldown_contract PASSED
```

---

## 5. Kết luận

Hệ thống **Screen Watcher Pro** đáp ứng đầy đủ các tiêu chuẩn kiểm thử đã đề ra trong [TESTING.md](file:///d:/AI/screen-watcher-pro/TESTING.md). Các ràng buộc bảo mật (RBAC), quản trị rule nghiêm ngặt (GR22-001/002/003/004), cùng cơ chế còi báo động SOS và xử lý sự kiện bất thường đều đạt độ phủ và kiểm chứng toàn diện ở mức unit/integration test offline.
