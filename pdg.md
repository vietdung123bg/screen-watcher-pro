# Product Design Guidelines (PDG)

# Rule Engine for Screen Watcher

Version: 1.0 Role: Product Manager Status: Draft

------------------------------------------------------------------------

# 1. Purpose

Rule Engine là thành phần quyết định một Event có trở thành Alert hay
không.

Mục tiêu của Rule Engine không phải chỉ "match keyword" mà là biến tín
hiệu quan sát được thành quyết định vận hành có thể tin cậy, giải thích
được, kiểm thử được và quản trị được.

Các nguyên tắc:

-   Explainable
-   Testable
-   Versioned
-   Auditable
-   Configurable
-   Observable

------------------------------------------------------------------------

# 2. Product Goals

## Functional Goals

-   Phân loại Event → Alert / Non Alert
-   Phân loại Severity
-   Deduplication
-   Suppression
-   Correlation
-   Evidence Generation
-   Rule Versioning

## Non Functional Goals

-   \< 100ms/rule evaluation (tham chiếu mục tiêu)
-   Stateless evaluation
-   Hot reload rule
-   Rollback rule
-   Full audit trail

------------------------------------------------------------------------

# 3. Domain Model

Event ↓ Normalization ↓ Rule Evaluation ↓ Suppression ↓ Deduplication ↓
Correlation ↓ Alert Decision ↓ Evidence

------------------------------------------------------------------------

# 4. Event Model

Ví dụ

``` json
{
  "eventId":"evt-001",
  "source":"screen",
  "screen":"grafana",
  "text":"CPU usage 95%",
  "confidence":0.96,
  "timestamp":"2026-07-08T09:30:00Z",
  "metadata":{
      "service":"payment-api",
      "env":"prod"
  }
}
```

Best Practice

-   Không phụ thuộc text thuần.
-   Chuẩn hóa field.
-   Metadata mở rộng.
-   Timestamp bắt buộc.

------------------------------------------------------------------------

# 5. Rule Model

Một Rule nên bao gồm

-   Rule ID
-   Name
-   Version
-   Priority
-   Enabled
-   Owner
-   Effective Date
-   Expired Date
-   Condition
-   Severity
-   Alert Type
-   Cooldown
-   Dedup Key
-   Tags

Ví dụ

``` yaml
ruleId: CPU_HIGH
version: 3
priority: 100

condition:
  all:
    - field: metadata.env
      op: eq
      value: prod

    - field: text
      op: contains
      value: CPU

severity: Critical
cooldown: 10m
```

------------------------------------------------------------------------

# 6. Supported Operators

-   eq
-   ne
-   gt
-   gte
-   lt
-   lte
-   contains
-   regex
-   startsWith
-   endsWith
-   in
-   notIn
-   exists

Khuyến nghị

Không lạm dụng Regex.

Ưu tiên structured field.

------------------------------------------------------------------------

# 7. Rule Evaluation Order

1 Event Validation

2 Normalization

3 Whitelist

4 Suppression

5 Rule Matching

6 Priority Resolution

7 Severity Override

8 Deduplication

9 Correlation

10 Alert Output

Không đảo thứ tự nếu chưa đánh giá tác động.

------------------------------------------------------------------------

# 8. Severity

Info

Warning

Minor

Major

Critical

Best Practice

Severity phản ánh tác động kinh doanh thay vì chỉ dựa vào keyword.

------------------------------------------------------------------------

# 9. Suppression

Ví dụ

Maintenance Window

Whitelist Host

Known Noise

Business Hours

Ví dụ

Không cảnh báo CPU cao trong thời gian backup.

------------------------------------------------------------------------

# 10. Deduplication

Ví dụ

CPU 95%

CPU 96%

CPU 97%

Trong 5 phút

=\> Một Alert

Dedup Key

service + alertType + severity

------------------------------------------------------------------------

# 11. Correlation

Ví dụ

Disk Full

↓

Database Down

↓

Application Timeout

↓

Một Incident

Không sinh ba Incident độc lập nếu cùng nguyên nhân.

------------------------------------------------------------------------

# 12. Explainability

Mỗi Alert phải trả lời được

-   Rule nào match?
-   Điều kiện nào match?
-   Điều kiện nào không match?
-   Priority nào thắng?
-   Có suppression không?
-   Có dedup không?

Ví dụ

``` json
{
 "decision":"Alert",
 "matchedRule":"CPU_HIGH",
 "reason":"CPU >= 90",
 "severity":"Critical"
}
```

------------------------------------------------------------------------

# 13. Rule Lifecycle

Draft

↓

Testing

↓

Approved

↓

Active

↓

Deprecated

↓

Disabled

Mọi thay đổi phải tạo Version mới.

------------------------------------------------------------------------

# 14. Rule Testing

Mỗi Rule tối thiểu cần

Positive Test

Negative Test

Boundary Test

Conflict Test

Dedup Test

Suppression Test

Regression Test

Ví dụ

  Input    Expected
  -------- ----------
  CPU 95   Alert
  CPU 89   No Alert
  CPU 90   Alert

------------------------------------------------------------------------

# 15. Governance

Rule Owner

Reviewer

Approver

Audit Log

Rollback

Không chỉnh Rule trực tiếp trên Production.

------------------------------------------------------------------------

# 16. Metrics

Rule Hit Rate

False Positive

False Negative

Average Evaluation Time

Top Triggered Rules

Disabled Rules

Noisy Rules

------------------------------------------------------------------------

# 17. UX Recommendations

Nên có

-   Rule Simulator
-   Dry Run
-   Test Dataset
-   Rule Diff
-   Rule Dependency
-   Impact Preview

------------------------------------------------------------------------

# 18. Common Anti Patterns

-   Match keyword duy nhất
-   Regex phức tạp
-   Không version
-   Không test
-   Không evidence
-   Hardcode trong source code
-   Không owner
-   Không rollback

------------------------------------------------------------------------

# 19. Future Roadmap

Phase 1

Static Rule

Phase 2

Rule Package

Phase 3

Rule Marketplace

Phase 4

AI Rule Suggestion

Phase 5

Learning Rule Recommendation

AI chỉ nên đề xuất Rule. Quyết định cuối cùng vẫn thuộc Rule Engine và
quy trình phê duyệt.

------------------------------------------------------------------------

# 20. Acceptance Criteria

Một Rule Engine đạt yêu cầu khi:

-   Quyết định Alert nhất quán.
-   Giải thích được.
-   Có version.
-   Có rollback.
-   Có test.
-   Có audit.
-   Có metrics.
-   Có governance.
