# Test matrix (Phase 1)

Requirement id to tests. Paths are relative to `apps/api/tests/`. Types: **U** unit (no DB), **I** integration (real Postgres), **A** acceptance (`integration/acceptance/`, whole pipeline with fakes).
Run: `make test` (everything), `uv run pytest -m "not integration"` (unit only). Tests marked **xfail(strict)** document a known bug; see "Open bugs" at the end.

| Id | Test (file::name) | Type |
|---|---|---|
| FR-01 | integration/test_items_api.py::test_post_then_repeat | I |
| FR-01 | integration/acceptance/test_p1_school_erp.py::test_school_erp_brief_ends_awaiting_approval_with_catalog_backed_options | A |
| FR-01 | unit/schemas/test_ingest.py (ingest body shape, `extra=forbid`) | U |
| FR-02 | integration/test_items_api.py::test_post_then_repeat (202 then 200, one job) | I |
| FR-02 | integration/test_queue.py (single enqueue per item) | I |
| FR-02 | integration/test_item_cap_rules.py::test_repeat_of_stored_item_at_cap_is_still_200 (fixed in 30c173a, BUG-1) | I |
| FR-02 | integration/test_daily_cap_hard.py::test_bulk_inserts_exactly_the_remaining_quota, ::test_idempotent_repeats_do_not_spend_quota | I |
| FR-03 | integration/test_items_api.py::test_bulk_mixed_207, ::test_bulk_501_rows_is_422 | I |
| FR-03 | integration/test_item_cap_rules.py::test_bulk_over_cap_is_429_with_retry_after | I |
| FR-06 | integration/test_items_api.py::test_raw_is_untouched_and_hints_stored | I |
| FR-07 | integration/test_auth.py::test_rate_limit_429_with_retry_after (120/min path, 2 in test) | I |
| FR-07 | integration/test_auth.py::test_redis_error_falls_back_to_memory_and_still_limits | I |
| FR-07 | unit/security/test_rate_limit.py::test_memory_allows_up_to_limit_then_denies_with_retry_after | U |
| FR-07 | integration/test_items_api.py::test_daily_cap_429 | I |
| FR-07 | integration/test_item_cap_rules.py::test_cap_is_per_tenant, ::test_retry_after_points_at_next_utc_midnight, ::test_yesterdays_items_do_not_count | I |
| FR-10 | unit/normalise/test_service.py::test_structured_payload_uses_no_llm, ::test_unknown_payload_calls_normalise_once | U |
| FR-10 | integration/acceptance/test_item_schema_conformance.py::test_processed_item_validates_against_the_published_schema_ignoring_nulls, ::test_punjabi_item_is_detected_and_still_conforms | A |
| FR-10 | integration/acceptance/test_item_schema_conformance.py::test_api_output_validates_as_is_against_the_published_schema (fixed in 30c173a, BUG-2) | A |
| FR-11 | unit/normalise/test_mappers.py::test_hints_mapper_wins_with_title_and_body, ::test_school_erp_text_dict_uses_structured_mapper, ::test_source_specific_mapper_registered | U |
| FR-12 | unit/normalise/test_service.py::test_llm_failure_falls_back_never_raises | U |
| FR-12 | unit/llm/test_structured.py (one repair retry), unit/llm/test_gateway.py::test_private_json_reaches_only_private_even_after_repair | U |
| FR-13 | unit/normalise/test_language.py::test_detect_language, ::test_one_hindi_function_word_is_still_english | U |
| FR-13 | unit/normalise/test_service.py::test_hint_language_beats_llm_and_heuristic, ::test_heuristic_language_on_gurmukhi | U |
| FR-20 | unit/triage/test_service.py::test_forty_items_one_laya_call_shadow_default | U |
| FR-20 | unit/triage/test_questions.py::test_core_questions_cover_four_ids_with_niche_descriptions, ::test_twelve_niches_ok_thirteen_error | U |
| FR-20 | unit/triage/test_laya_client.py::test_chunks_70_states_into_32_32_6_and_keeps_order | U |
| FR-21 | unit/triage/test_service.py::test_hinted_niche_sets_hint_source_and_asks_niche_questions_in_same_call, ::test_unhinted_niche_questions_get_second_laya_call_per_group | U |
| FR-22 | unit/triage/test_service_rules.py::test_every_stored_answer_has_choice_probabilities_confidence_and_model | U |
| FR-22 | unit/triage/test_service_rules.py::test_spam_discard_threshold (0.84 kept, 0.85 and 0.99 discarded), ::test_scam_is_never_discarded_even_when_certain, ::test_discarded_item_keeps_its_triage_record | U |
| FR-22 | unit/triage/test_service.py::test_spam_is_discarded_and_scam_is_kept_with_risk | U |
| FR-23 | unit/triage/test_modes.py::test_defaults_to_shadow, ::test_tenant_beats_env, ::test_niche_override_beats_tenant | U |
| FR-23 | unit/triage/test_service.py::test_off_mode_never_calls_laya, ::test_on_mode_confident_laya_needs_no_llm, ::test_on_mode_low_confidence_questions_go_to_fallback | U |
| FR-23 | integration/acceptance/test_p7_laya_never_on.py (repo never defaults to on) | A |
| FR-24 | unit/triage/test_service.py::test_shadow_laya_down_records_error_and_uses_llm, ::test_on_mode_laya_down_uses_llm, ::test_laya_and_llm_down_needs_human_triage | U |
| FR-24 | unit/triage/test_service_rules.py::test_human_triage_item_has_error_and_no_niche | U |
| FR-24 | integration/acceptance/test_p4_laya_down.py (4 tests: shadow, on, both down, HttpLayaClient on closed port with 10 items) | A |
| FR-25 | unit/graph/test_policy.py::test_scam_forces_suggest_with_warning, ::test_low_confidence_scam_does_not_force | U |
| FR-25 | unit/triage/test_service_rules.py::test_scam_boundary_is_inclusive_at_point_eight, ::test_non_scam_risk_is_never_scam, ::test_scam_overrides_auto_autonomy_with_allow_listed_action | U |
| FR-25 | unit/triage/test_service.py::test_fallback_spam_parks_when_laya_shadow_below_threshold, ::test_fallback_spam_discards_when_laya_shadow_agrees | U |
| FR-30 | unit/graph/test_route.py::test_choose_route, ::test_route_node_applies_status_and_niche | U |
| FR-30 | integration/acceptance/test_p1_school_erp.py (niche=tech_stack) | A |
| FR-31 | unit/graph/test_decide.py::test_decide_drops_actions_outside_niche_and_keeps_empty_option | U |
| FR-31 | integration/acceptance/test_p1_school_erp.py (2 to 5 options, recommended in ids, rationale at most 3 sentences) | A |
| FR-32 | unit/tools/test_registry.py::test_cache_hit_and_expiry, ::test_private_item_skips_non_private_ok_tool | U |
| FR-32 | unit/tools/test_stack_catalog.py (offline/zero-budget ranking, dated entries) | U |
| FR-33 | integration/test_graph_resume.py::test_run_waits_for_approval_and_resume_finishes, ::test_second_resume_is_not_awaiting | I |
| FR-33 | integration/test_decision_api.py::test_double_submit_gives_one_200_and_one_409, ::test_concurrent_submits_one_wins, ::test_busy_item_is_409_item_busy | I |
| FR-33 | integration/acceptance/test_p3_crash_resume.py (resume from checkpoint, extract called once) | A |
| FR-34 | unit/graph/test_builder.py::test_suggest_autonomy_approve_runs_no_actions, ::test_auto_autonomy_approves_only_allow_listed_actions, ::test_auto_autonomy_with_action_outside_auto_actions_asks | U |
| FR-34 | unit/graph/test_policy.py::test_niche_autonomy_is_kept | U |
| FR-35 | unit/graph/test_oneshot.py (Laya answers with no LLM, fallback, explain) | U |
| FR-35 | integration/test_decide_api.py::test_laya_answers_with_no_llm_call_and_no_rows, ::test_private_without_private_provider_is_503, ::test_fallback_unavailable_is_503, ::test_slow_laya_times_out_with_504, ::test_requires_decide_scope | I |
| FR-35 | integration/test_decide_quota.py::test_limit_plus_one_call_is_429_with_retry_after, ::test_counter_is_per_tenant, ::test_concurrent_calls_never_exceed_limit | I |
| FR-35 | unit/graph/test_oneshot.py::test_default_shadow_mode_answers_from_fallback_and_reports_laya_as_shadow | U |
| FR-35 | integration/test_decide_api.py::test_default_shadow_mode_reports_laya_only_as_shadow | I |
| FR-40 | unit/actions/test_registry.py::test_generic_actions_registered_and_no_unsafe_ones, ::test_params_models_forbid_extra_and_have_no_url_or_email_fields | U |
| FR-40 | integration/test_actions.py::test_remind_enqueues_job_and_reminder_due_emits_action_done, ::test_create_task_uses_item_title | I |
| FR-41 | unit/actions/test_registry.py::test_idem_key_is_sha256_of_item_action_canonical_params, ::test_idem_key_differs_by_params_and_action | U |
| FR-41 | integration/test_actions.py::test_same_params_twice_one_row_same_result, ::test_different_params_two_rows | I |
| FR-41 | integration/test_action_retry.py::test_raising_action_is_recorded_failed_and_not_rerun_on_retry, ::test_success_retry_returns_stored_data_without_rerunning, ::test_same_action_on_another_item_runs_again | I |
| FR-42 | unit/integrations/test_envelope.py::test_failure_schedules_retry (1m/5m/30m/2h), ::test_fifth_failure_is_dead_letter, ::test_redirect_is_a_failure_and_not_followed | U |
| FR-42 | integration/test_webhook_dead_letter.py::test_five_failures_follow_the_ladder_then_dead_letter | I |
| FR-42 | integration/test_webhooks_out.py::test_fanout_one_delivery_per_subscription_and_deliver | I |
| FR-42 | unit/test_sdk_signature_compat.py, security/test_hmac.py (signature, 5-min skew) | U |
| FR-42 | integration/acceptance/test_p2_approve_webhook.py (signed delivery, 500 then retry in 60 s) | A |
| FR-42 | unit/integrations/test_delivery_hardening.py::test_slow_receiver_is_cut_off_by_total_timeout, ::test_oversized_2xx_body_is_cut_off_and_still_delivered | U |
| FR-42 | integration/test_webhook_lock_not_held.py::test_second_session_can_update_row_during_the_post | I |
| FR-42 | unit/integrations/test_delivery_crypto_errors.py::test_corrupt_secret_dead_letters_without_request | U |
| FR-54 | integration/test_feedback.py::test_one_decision_one_row_and_export | I |
| FR-54 | integration/test_decision_timing_feedback.py::test_approve_stores_time_to_decide_on_decision_and_feedback, ::test_reject_with_note_is_recorded_as_a_correction_label | I |
| FR-54 | integration/test_feedback.py::test_snooze_then_approve_exports_one_line_and_auto_is_excluded | I |
| FR-54 | unit/feedback/test_export.py::test_reject_does_not_write_triage_answer_as_needs_decision_gold, ::test_snooze_rows_never_carry_answer_gold | U |
| FR-60 | integration/test_llm_usage.py::test_postgres_store_incr_first_enforces_limit_under_concurrency | I |
| FR-62 | integration/test_corrections_sensitivity.py::test_public_call_excludes_private_rows, ::test_private_call_sees_both | I |
| FR-73 | unit/niches/test_evals_files.py::test_row_count_and_format, ::test_balanced_and_multilingual | U |
| FR-80 | unit/feedback/test_export.py::test_laya_train_line_has_gold_probabilities_and_no_raw, ::test_laya_eval_line_has_expected_keys | U |
| FR-80 | integration/test_feedback_api.py::test_export_streams_ndjson, ::test_export_rejects_unknown_format | I |
| FR-96 | integration/test_decide_api.py (radar bridge call shape), unit/test_sdk_client_retries.py | I |
| FR-111 | integration/test_auth.py::test_valid_key_authenticates, ::test_revoked_key_is_401, ::test_missing_scope_403_and_admin_implies_all, ::test_key_never_stored_or_logged_in_plain_text | I |
| FR-111 | unit/security/test_api_keys.py | U |
| NFR-02 | unit/test_deploy_contract.py::test_worker_batch_never_exceeds_32 | U |
| NFR-02 | integration/test_queue.py::test_two_sessions_claim_disjoint_jobs | I |
| NFR-03 | integration/acceptance/test_p4_laya_down.py, integration/acceptance/test_p3_crash_resume.py | A |
| NFR-03 | integration/test_queue.py::test_five_failures_end_in_failed_with_growing_backoff, integration/test_worker_lifecycle.py::test_crashed_worker_job_is_reclaimed_and_finished_by_next_worker | I |
| NFR-05 | unit/integrations/test_ssrf.py, unit/integrations/test_ssrf_bypass_and_delivery.py (bypass forms, DNS rebinding, refusal at delivery without a request) | U |
| NFR-05 | integration/test_subscriptions_api.py::test_loopback_url_is_422, integration/test_webhooks_out.py::test_private_url_rejected_when_not_allowed | I |
| NFR-05 | security/test_crypto.py, security/test_hmac.py, unit/security/test_api_keys.py | U |
| NFR-05 | integration/test_body_limits.py::test_oversized_content_length_is_413_problem_json, ::test_streamed_body_without_content_length_is_413, ::test_bulk_uses_the_larger_limit | I |
| NFR-06 (privacy, Phase 1 scope) | unit/llm/test_privacy.py, unit/llm/test_privacy_matrix.py (every purpose, no private_ok provider means zero calls) | U |
| NFR-06 | integration/acceptance/test_private_pipeline.py::test_every_llm_call_for_a_private_item_is_private_and_fenced, ::test_no_private_provider_never_loses_the_item | A |
| NFR-06 | unit/graph/test_decide.py::test_private_item_uses_private_sensitivity, unit/normalise/test_service.py::test_private_item_passes_private_sensitivity, unit/triage/test_fallback.py::test_private_item_calls_with_private_and_fences_content | U |
| NFR-07 | unit/llm/test_fence.py, security/test_untrusted.py (control chars, cap, fence forging) | U |
| NFR-07 | unit/security/test_prompt_paths_fenced.py::test_every_gateway_caller_uses_fence, ::test_prompt_paths_exist, ::test_no_provider_sdk_outside_llm_package | U |
| NFR-07 | unit/graph/test_decide.py::test_decide_prompt_fences_content_and_carries_tool_as_of, unit/normalise/test_service.py::test_payload_is_fenced_as_data | U |
| NFR-07 | unit/actions/test_registry.py (no URL/email param fields), integration/test_actions.py | U |
| NFR-07 | unit/triage/test_log_privacy.py::test_laya_client_exception_not_logged, ::test_fallback_exception_not_logged | U |
| NFR-12 | unit/test_deploy_contract.py (compose services, profile for laya, Makefile targets) | U |
| NFR-12 | integration/test_migration.py::test_upgrade_downgrade_upgrade | I |
| NFR-12 | unit/test_scaffold.py (no provider SDK outside llm) | U |

## Open bugs (xfail strict)
- BUG-3 NFR-03: if `add_listener` raises after `asyncpg.connect` succeeded, the connection is never closed. `apps/api/app/workers/run.py` `_listen`. Test: `unit/workers/test_run_loop.py::test_listen_failure_after_connect_closes_the_connection`.
- BUG-1 (FR-02) and BUG-2 (FR-10) are fixed in 30c173a. Their tests no longer carry xfail.

## Not covered in Phase 1
- FR-34 "10 s undo" is not implemented in Phase 1 (only the `undone_at` column exists).
- FR-96 Opportunity Radar bridge is covered through `/v1/decide` and the SDKs; no radar-side test lives in this repo.
