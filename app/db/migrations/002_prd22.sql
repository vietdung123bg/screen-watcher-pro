-- ============================================================================
-- PRD 2.2 — AI Assisted Event Review & Rule Governance (Phase 1 MVP)
-- Adds 6 new tables. IDEMPOTENT: safe to run any number of times.
-- Existing tables are NOT modified. Applied by Database.apply_migrations(),
-- which backs the DB up to <db>.pre-prd22.bak before the first application.
-- ============================================================================

-- events: bridge from screenshots + ocr_results into the review workflow.
-- Status flow: NEW -> NORMALIZED -> EVALUATED -> MATCHED_RULE /
--   AI_REVIEW_PENDING -> AI_REVIEWED -> USER_REVIEW_PENDING ->
--   CONFIRMED_ISSUE / CONFIRMED_INCIDENT / IGNORED / CLOSED
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,                    -- UUIDv7
    event_id TEXT UNIQUE NOT NULL,          -- human-facing id (EVT-...)
    source TEXT NOT NULL,                   -- 'screen_watcher' | 'api' | 'mock'
    screen TEXT,
    screenshot_id TEXT,
    raw_text TEXT,
    normalized_json TEXT,
    metadata_json TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'NEW',
    event_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (screenshot_id) REFERENCES screenshots(id)
);

-- rules_db: DB-backed rules, parallel to config/rules.yaml (YAML rules are
-- synced in as ACTIVE created_by='yaml_sync').
-- Status flow: DRAFT -> AI_SUGGESTED -> USER_REVIEW_PENDING -> ACTIVE /
--   REJECTED / DISABLED. GR22-003: REJECTED rows are KEPT (+ reject_reason).
CREATE TABLE IF NOT EXISTS rules_db (
    id TEXT PRIMARY KEY,
    rule_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    owner_group TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    enabled INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 50,
    severity TEXT,
    alert_type TEXT,
    rule_type TEXT NOT NULL,                -- contains|not_contains|regex|all_keywords|any_keywords
    condition_json TEXT NOT NULL,           -- {"value":..}|{"pattern":..}|{"keywords":[..]} + ignore_case
    is_incident_rule INTEGER DEFAULT 0,     -- GR22-002: only user-approved rules may be 1 + ACTIVE
    cooldown_seconds INTEGER DEFAULT 300,
    reject_reason TEXT,                     -- GR22-003
    created_by TEXT,                        -- username | 'ai_review' | 'yaml_sync'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ai_event_reviews: level-1 AI review of one event.
-- status: PENDING | REVIEWED | USER_REVIEWED | FAILED | RETRY_REQUIRED
CREATE TABLE IF NOT EXISTS ai_event_reviews (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    classification TEXT,
    risk_level TEXT,                        -- LOW | MEDIUM | HIGH | CRITICAL
    confidence REAL,                        -- 0..1
    reason TEXT,
    suggested_action TEXT,                  -- IGNORE|MONITOR|CREATE_DRAFT_RULE|ESCALATE_TO_USER
    suggested_rule_json TEXT,
    suggested_rule_id TEXT,                 -- rules_db.id of the created draft (if any)
    model_name TEXT,
    prompt_version TEXT,
    status TEXT DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events(id)
);

-- user_review_decisions: level-2 user decision over an AI review.
-- decision: APPROVE | EDIT | REJECT | IGNORE
CREATE TABLE IF NOT EXISTS user_review_decisions (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    ai_review_id TEXT,
    decision TEXT NOT NULL,
    edited_rule_json TEXT,
    reject_reason TEXT,
    review_note TEXT,
    reviewed_by TEXT NOT NULL,
    reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- rule_test_results: outcome of testing one rule against one event / sample text.
CREATE TABLE IF NOT EXISTS rule_test_results (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    event_id TEXT,
    expected_decision TEXT,                 -- MATCH | NO_MATCH
    actual_decision TEXT,
    matched_conditions_json TEXT,
    failed_conditions_json TEXT,
    result_status TEXT,                     -- PASS | FAIL
    tested_by TEXT,
    tested_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- sos_alerts: audible incident alerts. The console SosWatcherJob polls PENDING
-- rows and beeps; acknowledge records who/when (GR22-004).
-- acknowledge_status: PENDING | ACKNOWLEDGED | CLOSED
CREATE TABLE IF NOT EXISTS sos_alerts (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    incident_id TEXT,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    sound_played INTEGER DEFAULT 0,
    last_beep_at DATETIME,
    acknowledge_required INTEGER DEFAULT 1,
    acknowledge_status TEXT DEFAULT 'PENDING',
    acknowledged_by TEXT,
    acknowledged_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sos_pending ON sos_alerts(acknowledge_status, last_beep_at);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_rules_db_status ON rules_db(status, enabled);
CREATE INDEX IF NOT EXISTS idx_ai_reviews_event ON ai_event_reviews(event_id, status);
CREATE INDEX IF NOT EXISTS idx_user_reviews_event ON user_review_decisions(event_id);
