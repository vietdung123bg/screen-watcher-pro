# Business Process Design (BPD)
# Thiết kế Quy trình Nghiệp vụ cho Rule Engine của Screen Watcher

**Phiên bản tài liệu:** 1.0  
**Loại tài liệu:** Business Process Design  
**Vai trò biên soạn:** Senior Business Analyst  
**Đối tượng sử dụng:** Product Owner, Operation Lead, SRE, Business Analyst, Rule Owner, Solution Architect, Development Team, QA Team  
**Phạm vi:** Thiết kế quy trình nghiệp vụ cho việc quản lý, quản trị, kiểm thử, phê duyệt, triển khai, giám sát và cải tiến liên tục các rule được sử dụng bởi Rule Engine trong ứng dụng Screen Watcher.

---

# 1. Executive Summary

Rule Engine không chỉ là một thành phần kỹ thuật dùng để đánh giá một event có phải là alert hay không. Rule Engine là một năng lực nghiệp vụ giúp chuyển hóa tri thức vận hành thành các rule có kiểm soát, có thể kiểm thử, có thể giải thích và có thể đo lường.

Tài liệu này định nghĩa quy trình nghiệp vụ cần thiết để vận hành Rule Engine một cách hiệu quả.

Quy trình nghiệp vụ cốt lõi là:

```text
Event được quan sát
    ↓
Issue được xác định
    ↓
Đánh giá nhu cầu tạo hoặc thay đổi rule
    ↓
Thiết kế rule
    ↓
Review rule
    ↓
Kiểm thử rule
    ↓
Phê duyệt rule
    ↓
Publish rule
    ↓
Giám sát rule
    ↓
Cải tiến hoặc ngừng sử dụng rule
```

Mục tiêu chính là bảo đảm mọi rule đều có mục đích nghiệp vụ rõ ràng, có owner, có luồng phê duyệt, có bằng chứng kiểm thử, có kiểm soát triển khai, có audit trail và có giá trị vận hành có thể đo lường.

---

# 2. Diagnosis

## 2.1 Problem Statement

Screen Watcher phát hiện các event dạng hình ảnh hoặc text từ các màn hình được giám sát. Tuy nhiên, không phải event nào cũng nên trở thành alert.

Do đó, cần có một quy trình nghiệp vụ để quản trị cách rule được tạo mới, thay đổi, review, phê duyệt, kiểm thử, triển khai, giám sát và ngừng sử dụng.

Nếu không có quy trình này, Rule Engine rất dễ trở thành một tập hợp rule thiếu nhất quán, gây nhiễu và khó tin cậy.

## 2.2 Technical Problem

Vấn đề kỹ thuật là các event sinh ra từ việc quan sát màn hình có thể:

* Nhiễu.
* Bị trùng lặp.
* Không có cấu trúc rõ ràng.
* Có nhiều nghĩa khác nhau tùy ngữ cảnh.
* Sai do OCR hoặc lỗi capture.
* Phụ thuộc vào ngữ cảnh vận hành.
* Lặp lại trong maintenance window.
* Giống với issue cũ nhưng không hoàn toàn giống.

Vì vậy, quản lý rule không thể được xem là việc chỉnh sửa cấu hình đơn giản.

## 2.3 Business Problem

Vấn đề nghiệp vụ là rule không đáng tin cậy có thể tạo ra rủi ro vận hành:

* Quá nhiều false alert gây alert fatigue.
* Bỏ sót alert thật làm chậm phản ứng với incident.
* Thay đổi rule không kiểm soát có thể tạo nhiễu trên production.
* Thiếu ownership làm rule bị lỗi thời.
* Thiếu evidence làm giảm niềm tin vào alert.
* Thiếu governance khiến audit và compliance khó thực hiện.

## 2.4 Observed Symptoms

Các triệu chứng thường gặp khi governance rule yếu:

* Operator bỏ qua alert vì có quá nhiều false positive.
* Nhiều team tạo rule trùng nhau.
* Không ai biết vì sao một rule tồn tại.
* Một rule vẫn trigger dù hệ thống liên quan đã decommission.
* Thay đổi rule làm hỏng hành vi alert hiện có.
* Không có test evidence cho rule đang chạy production.
* Severity của alert không nhất quán giữa các team.
* Cùng một event tạo ra nhiều ticket.

## 2.5 Available Evidence

Các concept thiết kế đã có từ phân tích trước:

* Rule Engine nhận event từ Screen Watcher.
* Rule Engine quyết định event có phải alert hay không.
* Quyết định phải giải thích được.
* Rule lifecycle nên gồm Draft, Testing, Approved, Active, Deprecated và Disabled.
* Rule cần hỗ trợ versioning, testing, rollback, suppression, deduplication và evidence.
* Cần phân biệt rõ Event, Alert, Incident, Issue và Problem.

## 2.6 Unknown Information

Các thông tin sau cần được xác nhận trong quá trình triển khai:

* Event schema hiện tại.
* Alert taxonomy hiện tại.
* Công cụ incident management hiện tại.
* Quy trình phê duyệt hiện tại.
* Cơ cấu đội vận hành hiện tại.
* Rule author là người kỹ thuật hay non technical.
* Thay đổi rule có được deploy ngay hay phải qua release window.
* Có cần phê duyệt từ khách hàng hay không.
* Có ràng buộc regulatory hoặc audit nào không.

---

# 3. Business Objectives

## 3.1 Primary Objectives

Quy trình nghiệp vụ của Rule Engine phải bảo đảm rằng:

* Rule chỉ được tạo khi có nhu cầu nghiệp vụ hoặc vận hành hợp lệ.
* Rule được review trước khi dùng trên production.
* Rule được kiểm thử bằng positive case và negative case.
* Rule được version hóa và có khả năng rollback.
* Rule có owner.
* Rule có evidence.
* Rule được giám sát sau khi active.
* Rule được cải tiến hoặc retire dựa trên dữ liệu thực tế.

## 3.2 Secondary Objectives

Quy trình cũng cần hỗ trợ:

* Tái sử dụng các rule pattern đã có.
* Onboard có kiểm soát các nhóm rule mới.
* Giảm false positive.
* Giảm false negative.
* Phát hiện incident nhanh hơn.
* Lưu giữ tri thức vận hành tốt hơn.
* Cải tiến liên tục dựa trên feedback từ incident và alert.

---

# 4. Scope

## 4.1 In Scope

Tài liệu BPD này bao gồm:

* Rule request intake.
* Rule qualification.
* Rule design.
* Rule review.
* Rule testing.
* Rule approval.
* Rule publication.
* Rule monitoring.
* Rule tuning.
* Rule retirement.
* Rule governance.
* Rule metrics.
* Rule audit.
* Rule ownership.
* Rule lifecycle.
* Rule exception handling.

## 4.2 Out of Scope

Tài liệu BPD này không bao gồm:

* Thiết kế source code chi tiết.
* Đặc tả UI chi tiết.
* Physical database schema.
* Thiết kế triển khai hạ tầng.
* Cài đặt OCR.
* Thuật toán screen capture.
* Quy trình xử lý incident sau khi alert được tạo.
* Cài đặt auto remediation.

---

# 5. Key Concepts

## 5.1 Event

Event là một tín hiệu được quan sát bởi Screen Watcher.

Ví dụ:

```text
CPU usage 95% trên dashboard của payment api
```

## 5.2 Alert

Alert là event cần được chú ý theo các rule đã được phê duyệt.

Ví dụ:

```text
Phát hiện CPU usage mức Critical cho payment api trên production
```

## 5.3 Incident

Incident là sự gián đoạn hoặc suy giảm ngoài kế hoạch của dịch vụ.

Ví dụ:

```text
Payment service không khả dụng với người dùng cuối
```

## 5.4 Issue

Issue là một hạng mục được theo dõi và cần điều tra, hành động hoặc ra quyết định.

Ví dụ:

```text
Điều tra alert CPU lặp lại trên dashboard payment api
```

## 5.5 Problem

Problem là nguyên nhân gốc bên dưới một hoặc nhiều incident.

Ví dụ:

```text
Memory leak trong payment api gây CPU saturation
```

## 5.6 Rule

Rule là một đơn vị logic nghiệp vụ có kiểm soát, dùng để quyết định event có nên tạo alert hay không.

Ví dụ:

```text
Nếu environment là production, confidence lớn hơn 0.8 và CPU usage lớn hơn hoặc bằng 90%, tạo alert Critical.
```

## 5.7 Rule Package

Rule Package là nhóm các rule liên quan được quản lý và release cùng nhau.

Ví dụ:

```text
Database Monitoring Rules v1.3
Application Availability Rules v2.1
```

---

# 6. Business Capability Map

```text
Rule Engine Business Capability
│
├── Rule Intake Management
├── Rule Design Management
├── Rule Review Management
├── Rule Testing Management
├── Rule Approval Management
├── Rule Publishing Management
├── Rule Monitoring Management
├── Rule Improvement Management
├── Rule Retirement Management
├── Rule Governance Management
├── Rule Audit Management
└── Rule Knowledge Management
```

## 6.1 Capability Description

| Capability | Mô tả |
|---|---|
| Rule Intake Management | Tiếp nhận và đánh giá yêu cầu tạo mới hoặc thay đổi rule |
| Rule Design Management | Xác định condition, severity, scope và evidence của rule |
| Rule Review Management | Review tính đúng đắn và tác động vận hành của rule |
| Rule Testing Management | Xác minh hành vi rule trước khi active |
| Rule Approval Management | Bảo đảm rule được business và operation phê duyệt trước khi dùng production |
| Rule Publishing Management | Kích hoạt rule theo cách có kiểm soát |
| Rule Monitoring Management | Theo dõi hiệu quả của rule sau khi active |
| Rule Improvement Management | Tinh chỉnh rule dựa trên feedback và metrics |
| Rule Retirement Management | Disable hoặc deprecate rule lỗi thời |
| Rule Governance Management | Quản lý policy, ownership, RACI và quy trình change |
| Rule Audit Management | Bảo đảm traceability và compliance evidence |
| Rule Knowledge Management | Liên kết rule với incident, RCA, SOP và runbook |

---

# 7. Stakeholders and Personas

## 7.1 Product Owner

Chịu trách nhiệm về định hướng sản phẩm, ưu tiên backlog và giá trị nghiệp vụ.

Nhu cầu:

* Roadmap năng lực rule.
* Dashboard KPI.
* Visibility về approval.
* Visibility về rủi ro.

## 7.2 Operation Lead

Chịu trách nhiệm về chất lượng alert và phản ứng vận hành.

Nhu cầu:

* Alert đáng tin cậy.
* Severity rõ ràng.
* Ít noise.
* Ownership của rule rõ ràng.
* Escalation rõ ràng.

## 7.3 Rule Owner

Chịu trách nhiệm về tính đúng đắn và bảo trì của một rule hoặc một nhóm rule.

Nhu cầu:

* Rule template.
* Công cụ test.
* Metrics sử dụng rule.
* Feedback về false positive.

## 7.4 Rule Author

Người tạo mới hoặc chỉnh sửa rule.

Nhu cầu:

* Hướng dẫn viết rule.
* Rule simulator.
* Feedback validation.
* Ví dụ cụ thể.

## 7.5 Reviewer

Người review chất lượng rule trước approval.

Nhu cầu:

* Rule diff.
* Test evidence.
* Impact preview.
* Conflict check.

## 7.6 Approver

Người phê duyệt việc active rule.

Nhu cầu:

* Business justification.
* Risk assessment.
* Kết quả kiểm thử.
* Rollback plan.

## 7.7 SRE hoặc Platform Engineer

Bảo đảm Rule Engine hoạt động tin cậy và có hiệu năng tốt.

Nhu cầu:

* Execution metrics.
* Error logs.
* Rule evaluation traces.
* Rollback capability.

## 7.8 QA Engineer

Xác minh hành vi của rule.

Nhu cầu:

* Test dataset.
* Expected result.
* Regression suite.
* Replay capability.

## 7.9 Incident Manager

Sử dụng alert output để quản lý incident.

Nhu cầu:

* Alert evidence rõ ràng.
* Alert correlation.
* Severity nhất quán.
* Thông tin rule liên quan.

---

# 8. RACI Matrix

| Activity | Product Owner | Operation Lead | Rule Owner | Rule Author | Reviewer | Approver | SRE | QA |
|---|---|---|---|---|---|---|---|---|
| Submit rule request | C | A | R | R | I | I | I | I |
| Qualify rule request | A | R | R | C | C | I | C | C |
| Design rule | C | C | A | R | C | I | C | C |
| Review rule | C | A | R | C | R | I | C | C |
| Test rule | I | C | A | C | C | I | C | R |
| Approve rule | A | R | C | I | C | R | I | I |
| Publish rule | I | A | C | I | I | C | R | C |
| Monitor rule | C | A | R | I | I | I | R | C |
| Tune rule | C | A | R | R | C | C | C | C |
| Retire rule | A | R | R | I | C | C | C | I |

Chú thích:

* R là Responsible.
* A là Accountable.
* C là Consulted.
* I là Informed.

Best practice:

* Mỗi active rule phải có đúng một Rule Owner chịu trách nhiệm chính.
* Rule Author và Approver không nên là cùng một người đối với production critical rule.
* Operation Lead nên chịu trách nhiệm về chất lượng alert.
* Product Owner nên chịu trách nhiệm về ưu tiên nghiệp vụ.

---

# 9. End to End Business Process

## 9.1 Process Overview

```text
Start
 ↓
Rule Request Submitted
 ↓
Rule Request Qualified
 ↓
Rule Designed
 ↓
Rule Reviewed
 ↓
Rule Tested
 ↓
Rule Approved
 ↓
Rule Published
 ↓
Rule Monitored
 ↓
Rule Improved or Retired
 ↓
End
```

## 9.2 Process Goals

Quy trình phải trả lời được các câu hỏi:

* Vì sao rule này cần thiết?
* Rule này đánh giá event nào?
* Rule này tạo ra alert nào?
* Rule này bảo vệ business impact nào?
* Ai sở hữu rule này?
* Rule này được kiểm thử như thế nào?
* Ai đã phê duyệt rule này?
* Rule này rollback như thế nào?
* Chất lượng rule sẽ được đo lường như thế nào?

---

# 10. Process 1: Rule Request Intake

## 10.1 Objective

Tiếp nhận nhu cầu tạo mới rule hoặc thay đổi rule hiện có.

## 10.2 Trigger

Một rule request có thể được kích hoạt bởi:

* Issue mới được phát hiện.
* Incident mới xảy ra.
* Khuyến nghị từ RCA.
* Yêu cầu từ khách hàng.
* Màn hình giám sát mới được onboard.
* Feedback về false positive.
* Feedback về false negative.
* Rủi ro vận hành được xác định.
* Yêu cầu compliance.
* Dashboard layout hoặc text trên màn hình thay đổi.

## 10.3 Input

Các thông tin bắt buộc:

| Field | Mô tả | Bắt buộc |
|---|---|---|
| Request ID | Mã yêu cầu duy nhất | Có |
| Request Type | New Rule, Change Rule, Disable Rule, Retire Rule | Có |
| Business Reason | Lý do cần rule | Có |
| Source Event Example | Ví dụ event hoặc text từ screenshot | Có |
| Expected Alert Behavior | Hành vi alert mong muốn | Có |
| Target System | Application, dashboard, screen hoặc service | Có |
| Environment | Prod, staging, test | Có |
| Priority | Mức ưu tiên nghiệp vụ | Có |
| Requester | Người hoặc team yêu cầu | Có |
| Deadline | Ngày cần hoàn thành | Không bắt buộc |
| Related Incident | Link incident hoặc RCA | Không bắt buộc |

## 10.4 Output

* Qualified rule request.
* Rejected request có lý do.
* Request cần bổ sung thông tin.

## 10.5 Decision Criteria

Một request nên được tiếp tục nếu:

* Có giá trị vận hành hoặc nghiệp vụ rõ ràng.
* Event có thể được phát hiện tương đối ổn định.
* Expected alert behavior được xác định.
* Có thể gán ownership.
* Rule không trùng với rule hiện có.

## 10.6 Best Practices

* Yêu cầu ít nhất một event example thực tế.
* Liên kết rule request với incident, issue, RCA hoặc business risk.
* Tránh chấp nhận yêu cầu mơ hồ như “alert toàn bộ error”.
* Kiểm tra rule catalog hiện có trước khi tạo rule mới.
* Phân loại request là detection, suppression, deduplication, severity change hoặc retirement.

## 10.7 Example

Request:

```text
Khi màn hình Grafana hiển thị CPU usage trên 90% cho production service, tạo alert Critical.
```

Qualification:

```text
Được chấp nhận vì CPU saturation đã từng gây degradation trên production và dashboard hiển thị CPU usage tương đối ổn định.
```

---

# 11. Process 2: Rule Qualification

## 11.1 Objective

Xác định rule request có hợp lệ, khả thi và không trùng lặp hay không.

## 11.2 Key Questions

* Đây có phải rủi ro vận hành thật không?
* Trường hợp này đã được rule hiện tại bao phủ chưa?
* Event có thể được phát hiện từ screen data không?
* Condition có đủ cụ thể không?
* Severity nào là phù hợp?
* Ai là owner của rule?
* Có cần suppression không?
* Có cần deduplication không?
* Có cần phê duyệt từ khách hàng hoặc internal operation team không?

## 11.3 Decision Outcomes

| Outcome | Ý nghĩa |
|---|---|
| Accept | Chuyển sang thiết kế rule |
| Reject | Không hợp lệ hoặc không hữu ích |
| Merge | Đã có rule tương tự nhưng cần điều chỉnh |
| Defer | Hợp lệ nhưng chưa ưu tiên |
| Need More Information | Thiếu input |

## 11.4 Example Rejection

Request:

```text
Tạo alert khi xuất hiện từ warning.
```

Decision:

```text
Reject vì condition quá rộng và sẽ tạo nhiều false positive. Requester cần cung cấp target screen, context, severity và operational action mong muốn.
```

## 11.5 Best Practices

* Tránh rule chỉ dựa trên một keyword.
* Yêu cầu alert phải actionable.
* Không tạo alert nếu không ai biết sau alert cần làm gì.
* Ưu tiên tuning rule hiện có thay vì tạo rule trùng.
* Đánh giá rủi ro false positive từ sớm.

---

# 12. Process 3: Rule Design

## 12.1 Objective

Chuyển yêu cầu nghiệp vụ đã qualified thành thiết kế rule cụ thể.

## 12.2 Rule Design Fields

| Field | Mô tả |
|---|---|
| Rule ID | Mã định danh ổn định và duy nhất |
| Rule Name | Tên dễ hiểu |
| Rule Description | Ý nghĩa nghiệp vụ |
| Rule Owner | Owner chịu trách nhiệm |
| Target Screen | Màn hình hoặc dashboard mục tiêu |
| Event Type | OCR, metric text, status text, visual state |
| Condition | Logic match |
| Severity | Mức độ cảnh báo |
| Alert Type | Capacity, Availability, Performance, Security, Data, Job Failure |
| Scope | Environment, service, tenant, region |
| Suppression Policy | Khi nào không alert |
| Deduplication Key | Cách gom alert trùng |
| Cooldown | Khoảng thời gian tối thiểu trước alert lặp lại |
| Evidence Required | Screenshot, text, field, confidence |
| Runbook Link | Hướng dẫn xử lý vận hành |
| Test Cases | Positive, negative và boundary tests |
| Rollback Plan | Cách quay lại version trước |
| Effective Date | Thời điểm rule có hiệu lực |
| Expiry Date | Thời điểm hết hiệu lực nếu có |

## 12.3 Rule Design Template

```yaml
ruleId: APP_CPU_HIGH_CRITICAL
name: Application CPU High Critical
description: Phát hiện CPU usage cao cho production application services
owner: Application Operation Team
targetScreen: Grafana Application Overview
eventType: OCR_TEXT
scope:
  env: prod
  serviceType: application

condition:
  all:
    - field: metadata.env
      operator: eq
      value: prod
    - field: extracted.metricName
      operator: eq
      value: cpu_usage
    - field: extracted.metricValue
      operator: gte
      value: 90
    - field: confidence
      operator: gte
      value: 0.80

alert:
  type: Capacity
  severity: Critical
  title: CPU usage is critically high
  message: CPU usage is above 90% for production service

deduplication:
  key: env + serviceName + alert.type
  cooldown: 10m

suppression:
  maintenanceWindow: true
  whitelist: false

evidence:
  includeOriginalText: true
  includeScreenshot: true
  includeMatchedFields: true

runbook: RUNBOOK-APP-CPU-HIGH
```

## 12.4 Best Practices

* Ưu tiên dùng structured extracted fields nếu có.
* Condition của rule phải dễ đọc.
* Severity mapping phải rõ ràng.
* Mỗi alert rule phải có deduplication key.
* Major và Critical rule cần có runbook hoặc action instruction.
* Tránh logic ẩn nằm ngoài rule definition.
* Với event từ OCR, cần có confidence threshold.
* Boundary condition phải được định nghĩa rõ.

---

# 13. Process 4: Rule Review

## 13.1 Objective

Xác minh tính đúng đắn, giá trị nghiệp vụ, rủi ro và khả năng bảo trì của rule trước khi kiểm thử và phê duyệt.

## 13.2 Review Checklist

| Review Area | Câu hỏi |
|---|---|
| Business Value | Rule có bảo vệ outcome nghiệp vụ hoặc vận hành thật không? |
| Actionability | Operator có thể hành động sau alert không? |
| Specificity | Condition đã đủ cụ thể chưa? |
| Severity | Severity có phù hợp với impact không? |
| Duplication | Đã có rule tương tự chưa? |
| Conflict | Có conflict với rule khác không? |
| Suppression | Có cần suppression trong maintenance không? |
| Deduplication | Event lặp lại có được gom không? |
| Evidence | Có đủ evidence để tin alert không? |
| Testability | Rule có thể kiểm thử được không? |
| Rollback | Rule có thể disable hoặc revert an toàn không? |

## 13.3 Review Outcomes

* Approved for testing.
* Requires design changes.
* Rejected.
* Merged with existing rule.
* Escalated for architecture review.

## 13.4 Best Practices

* Review rule diff, không chỉ review final rule.
* Review rủi ro false positive dự kiến.
* Review rủi ro false negative dự kiến.
* Review operational action sau alert.
* Bắt buộc có runbook cho Major và Critical alert.
* Có SRE tham gia review với rule có volume cao.
* Có Security tham gia review với rule liên quan bảo mật.

---

# 14. Process 5: Rule Testing

## 14.1 Objective

Bảo đảm rule hoạt động đúng như kỳ vọng trước khi active trên production.

## 14.2 Test Types

| Test Type | Mục đích |
|---|---|
| Positive Test | Event phải trigger alert |
| Negative Test | Event không được trigger alert |
| Boundary Test | Xác minh ngưỡng biên |
| Suppression Test | Xác minh hành vi maintenance hoặc whitelist |
| Deduplication Test | Xác minh việc gom event lặp |
| Conflict Test | Xác minh hành vi khi nhiều rule cùng match |
| Regression Test | Bảo đảm rule cũ không bị ảnh hưởng |
| Replay Test | Chạy rule trên historical event dataset |
| Dry Run Test | Evaluate rule trên production nhưng không tạo alert |

## 14.3 Minimum Test Requirement

Mỗi production rule phải có:

* Ít nhất một positive test.
* Ít nhất một negative test.
* Ít nhất một boundary test nếu rule có threshold.
* Ít nhất một deduplication test nếu alert có thể lặp.
* Ít nhất một suppression test nếu có maintenance window.

## 14.4 Example Test Cases

| Test ID | Input Event | Expected Result | Notes |
|---|---|---|---|
| TC-001 | CPU usage 95%, env prod, confidence 0.95 | Alert Critical | Positive |
| TC-002 | CPU usage 70%, env prod, confidence 0.95 | No Alert | Negative |
| TC-003 | CPU usage 90%, env prod, confidence 0.95 | Alert Critical | Boundary |
| TC-004 | CPU usage 95%, env prod, maintenance window active | Suppressed | Suppression |
| TC-005 | CPU usage 96%, cùng service trong 10 phút | Deduplicated | Deduplication |
| TC-006 | CPU usage 95%, env test | No Alert | Scope test |

## 14.5 Test Evidence

Mỗi lần test execution cần lưu:

* Test ID.
* Rule version.
* Input event.
* Expected result.
* Actual result.
* Execution time.
* Tester.
* Execution date.
* Evidence attachment.
* Pass hoặc fail status.

## 14.6 Best Practices

* Ưu tiên dùng event lịch sử thực tế.
* Duy trì golden dataset cho regression.
* Test kỹ các non alert case.
* Replay rule trên ít nhất 7 đến 30 ngày historical events nếu có.
* Chạy high risk rule ở dry run mode trước khi active.
* Không approve rule nếu thiếu test evidence.

---

# 15. Process 6: Rule Approval

## 15.1 Objective

Bảo đảm chỉ các rule đã được review và test mới được active trên production.

## 15.2 Approval Requirements

Rule chỉ được approve nếu:

* Business reason được tài liệu hóa.
* Rule owner đã được gán.
* Review đã hoàn thành.
* Test đã pass.
* Severity đã được xác nhận.
* Rollback plan đã được tài liệu hóa.
* Impact đã được đánh giá.
* Deployment plan đã được thống nhất.

## 15.3 Approval Levels

| Rule Risk Level | Approval Requirement |
|---|---|
| Low | Rule Owner approval |
| Medium | Rule Owner và Operation Lead |
| High | Operation Lead và Product Owner |
| Critical | Product Owner, Operation Lead và SRE hoặc CAB |

## 15.4 Risk Level Criteria

| Risk Level | Criteria |
|---|---|
| Low | Chỉ Info hoặc Warning, volume thấp |
| Medium | Có thể tạo ticket hoặc tăng workload cho operator |
| High | Major hoặc Critical alert, business impact cao |
| Critical | Auto escalation, customer notification hoặc auto remediation |

## 15.5 Best Practices

* Tách Rule Author và Approver đối với production rule.
* Critical severity cần approval chặt hơn.
* High volume rule nên có dry run result.
* Approval record phải immutable.
* Approval nên hết hạn nếu rule không được publish trong thời gian đã thống nhất.

---

# 16. Process 7: Rule Publishing

## 16.1 Objective

Active rule đã được phê duyệt theo cách có kiểm soát và có traceability.

## 16.2 Publishing Modes

| Mode | Mô tả | Use Case |
|---|---|---|
| Manual Activation | Human active rule | Thay đổi không thường xuyên |
| Scheduled Activation | Rule active tại thời điểm định trước | Release window |
| Canary Activation | Rule active trên scope hẹp trước | High risk rule |
| Dry Run | Rule evaluate nhưng không tạo alert | Validate trên production |
| Shadow Mode | Output được lưu để so sánh | Rule thử nghiệm hoặc AI suggested rule |

## 16.3 Publishing Steps

```text
Xác nhận version đã approve
    ↓
Xác nhận test evidence
    ↓
Xác nhận rollback version
    ↓
Active rule
    ↓
Giám sát cửa sổ chạy đầu tiên
    ↓
Xác nhận không có alert volume bất thường
```

## 16.4 Best Practices

* Publish theo version, không publish mutable rule object.
* Dùng canary cho nhóm rule dễ gây noise.
* Dùng dry run trước khi active production với rule chưa chắc chắn.
* Thông báo operation team trước khi active high impact rule.
* Ghi nhận ai publish rule và publish lúc nào.
* Validate active rule checksum hoặc version sau deployment.

---

# 17. Process 8: Rule Monitoring

## 17.1 Objective

Đo lường chất lượng và giá trị vận hành của rule sau khi active.

## 17.2 Monitoring Metrics

| Metric | Ý nghĩa |
|---|---|
| Rule Hit Count | Số lần rule match |
| Alert Created Count | Số alert được tạo |
| Suppressed Count | Số match bị suppression |
| Deduplicated Count | Số event trùng được gom |
| False Positive Count | Alert bị đánh giá là không cần thiết |
| False Negative Count | Alert bị bỏ sót và phát hiện sau |
| Mean Evaluation Time | Thời gian execution trung bình |
| Top Noisy Rules | Các rule tạo quá nhiều alert |
| Rule Staleness | Rule lâu không trigger |
| Rule Coverage | Tỷ lệ known event types được rule bao phủ |
| Operator Feedback Score | Điểm đánh giá hữu ích từ operator |

## 17.3 Quality Threshold Examples

| Metric | Target |
|---|---|
| False Positive Rate | Dưới 5% cho Critical rules |
| Rule Evaluation Latency | Dưới 100ms mỗi event cho standard rules |
| Rule Owner Coverage | 100% active rules |
| Test Coverage | 100% active rules có tests |
| Runbook Coverage | 100% Major và Critical alerts |
| Review Cycle | Ít nhất mỗi quý cho critical rules |

## 17.4 Best Practices

* Theo dõi top noisy rules hằng tuần.
* Theo dõi rule không bao giờ trigger.
* Theo dõi alert bị đóng là non issue.
* Dùng feedback loop từ operator.
* Review high severity rule thường xuyên hơn.
* Đo giá trị rule, không chỉ đo activity.

---

# 18. Process 9: Rule Tuning and Continuous Improvement

## 18.1 Objective

Cải thiện accuracy của rule và giảm noise vận hành.

## 18.2 Tuning Triggers

Rule nên được tuning khi:

* False positive rate vượt ngưỡng.
* False negative được báo cáo.
* Source screen thay đổi.
* Event format thay đổi.
* Alert volume tăng đột biến.
* Operation team đánh giá alert ít hữu ích.
* Business impact thay đổi.
* Xuất hiện yêu cầu suppression mới.
* Incident liên quan cho thấy detection chưa đầy đủ.

## 18.3 Tuning Options

| Problem | Tuning Action |
|---|---|
| Quá nhiều false positives | Thêm context conditions |
| Bỏ sót alert | Mở rộng condition hoặc thêm alternate pattern |
| Alert trùng | Cải thiện dedup key hoặc cooldown |
| Sai severity | Cập nhật severity mapping |
| Noise trong maintenance | Thêm suppression window |
| OCR sai | Thêm confidence threshold hoặc fuzzy matching |
| Rule conflict | Điều chỉnh priority hoặc tách rule |
| Alert lỗi thời | Deprecate hoặc disable rule |

## 18.4 Example

Problem:

```text
Rule trigger khi dashboard hiển thị historical CPU spike trong chart, không phải current CPU.
```

Tuning:

```text
Thêm condition event region phải là current status panel và timestamp phải nằm trong current monitoring window.
```

## 18.5 Best Practices

* Xem tuning là một controlled change.
* Không sửa trực tiếp production rule.
* Tạo rule version mới.
* Chạy lại regression tests.
* So sánh metrics trước và sau.
* Giữ version cũ để rollback.

---

# 19. Process 10: Rule Retirement

## 19.1 Objective

Loại bỏ rule lỗi thời hoặc có giá trị thấp theo cách có kiểm soát.

## 19.2 Retirement Triggers

Rule có thể được retire khi:

* Hệ thống liên quan đã decommission.
* Screen không còn tồn tại.
* Rule được thay thế bởi rule tốt hơn.
* Rule không có hit trong thời gian dài.
* Rule liên tục tạo false positive.
* Rule không còn owner.
* Business process thay đổi.
* Monitoring source được thay thế bởi API metrics trực tiếp.

## 19.3 Retirement Process

```text
Xác định rule candidate cần retire
    ↓
Đánh giá usage và dependency
    ↓
Thông báo owner và stakeholders
    ↓
Chuyển rule sang Deprecated
    ↓
Theo dõi trong giai đoạn đã thống nhất
    ↓
Disable rule
    ↓
Archive evidence và history
```

## 19.4 Best Practices

* Không xóa lịch sử rule.
* Ưu tiên Deprecated trước Disabled.
* Giữ audit trail.
* Kiểm tra rule khác có phụ thuộc không.
* Xác nhận không có runbook active phụ thuộc rule đó.
* Review stale rules theo quý.

---

# 20. Rule Lifecycle

## 20.1 Lifecycle States

```text
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
```

## 20.2 State Description

| State | Ý nghĩa |
|---|---|
| Draft | Rule đang được thiết kế |
| Testing | Rule đang được kiểm thử |
| Approved | Rule đã approve nhưng chưa active |
| Active | Rule đang được dùng cho quyết định production |
| Deprecated | Rule không nên dùng cho scope mới và đang chờ retirement |
| Disabled | Rule không active nhưng được giữ lại để audit |

## 20.3 State Transition Rules

| From | To | Condition |
|---|---|---|
| Draft | Testing | Thiết kế hoàn tất |
| Testing | Draft | Test failed |
| Testing | Approved | Tất cả required tests pass |
| Approved | Active | Publish hoàn tất |
| Active | Deprecated | Có replacement hoặc retirement plan |
| Deprecated | Disabled | Kết thúc observation period |
| Active | Disabled | Emergency disable |
| Active | Draft | Cần version mới |

## 20.4 Best Practices

* Production change phải tạo version mới.
* Disabled không có nghĩa là deleted.
* Emergency disable phải có post action review.
* Deprecated state nên có expiry date.

---

# 21. Business Rules for Rule Governance

## 21.1 Mandatory Governance Rules

1. Mỗi active rule phải có một owner.
2. Mỗi active rule phải có một approved version.
3. Mỗi active rule phải có test evidence.
4. Mỗi Major hoặc Critical rule phải có runbook.
5. Mỗi rule change phải tạo audit record.
6. Mỗi rule phải có rollback option.
7. Mỗi rule phải có severity và alert type.
8. Mỗi alert phải có matched rule evidence.
9. Production rule không được edit trực tiếp.
10. Disabled rule phải vẫn auditable.

## 21.2 Optional Governance Rules

1. High risk rules yêu cầu dry run.
2. Critical rules yêu cầu quarterly review.
3. Rule không có hit trong 90 ngày được đánh dấu stale.
4. Rule có false positive rate cao được tự động flag để review.
5. AI suggested rules phải qua human approval.

---

# 22. Rule Taxonomy

## 22.1 Alert Type Taxonomy

| Alert Type | Mô tả | Ví dụ |
|---|---|---|
| Availability | Dịch vụ không khả dụng | Service down |
| Performance | Dịch vụ chậm | Response time cao |
| Capacity | Resource gần hoặc vượt ngưỡng | CPU, RAM, disk cao |
| Security | Tín hiệu liên quan bảo mật | Unauthorized access |
| Data | Data quality hoặc sync issue | Count mismatch |
| Job Failure | Batch hoặc scheduled task fail | ETL failed |
| Integration | Vấn đề dependency bên ngoài | API timeout |
| Configuration | Lỗi cấu hình | Sai endpoint |
| Compliance | Vi phạm policy hoặc control | Thiếu audit log |

## 22.2 Severity Taxonomy

| Severity | Ý nghĩa nghiệp vụ | Ví dụ |
|---|---|---|
| Info | Thông tin, không cần hành động ngay | Deployment completed |
| Warning | Cần chú ý nhưng chưa có impact trực tiếp | Disk 75% |
| Minor | Impact hạn chế hoặc early degradation | Một replica unhealthy |
| Major | Degradation đáng kể | API error rate cao |
| Critical | Impact production nghiêm trọng hoặc outage sắp xảy ra | Payment unavailable |

## 22.3 Best Practices

* Severity phải phản ánh business impact.
* Không dùng wording kỹ thuật đơn lẻ để quyết định severity.
* Severity cần align với incident management process.
* Dùng cùng severity taxonomy giữa các team.

---

# 23. Decision Points

## 23.1 Should an Event Become an Alert?

Decision logic:

```text
Event có hợp lệ không?
    ↓
Event có nằm trong monitored scope không?
    ↓
Event có đang bị suppression không?
    ↓
Event có match active rule không?
    ↓
Alert có actionable không?
    ↓
Đây có phải duplicate không?
    ↓
Create hoặc update alert
```

## 23.2 Should a New Rule Be Created?

Chỉ tạo rule mới nếu:

* Existing rules không bao phủ case này.
* Event có thể detect đáng tin cậy.
* Có operational action sau alert.
* Giá trị nghiệp vụ hoặc vận hành rõ ràng.
* Owner đã được gán.

## 23.3 Should a Rule Be Disabled?

Disable rule nếu:

* Rule tạo false positives nghiêm trọng.
* Rule không có owner.
* Rule conflict với rule priority cao hơn.
* Source screen không còn hợp lệ.
* Rule gây alert storm.

## 23.4 Should a Rule Be Tuned?

Tune rule nếu:

* Rule hữu ích nhưng chưa chính xác.
* Condition quá rộng hoặc quá hẹp.
* Severity sai.
* Thiếu suppression hoặc deduplication.

---

# 24. Exception Handling Process

## 24.1 Emergency Rule Disable

Trigger:

* Rule gây alert storm.
* Rule tạo noise vận hành cao.
* Rule làm nghẽn downstream process.
* Rule gây customer notification sai.

Process:

```text
Operation Lead yêu cầu emergency disable
    ↓
SRE disable active rule version
    ↓
Tạo incident hoặc change record
    ↓
Thông báo stakeholders
    ↓
Thực hiện post action review
    ↓
Rule được fix, retire hoặc restore
```

Best practice:

* Emergency disable phải auditable.
* Root cause phải được review.
* Rule không được reactivate nếu không có test evidence.

## 24.2 Rule Conflict

Ví dụ:

```text
Rule A quy định CPU > 90 = Critical
Rule B quy định CPU > 85 trong batch window = Warning
```

Các hướng xử lý:

* Tăng priority của rule cụ thể hơn.
* Thêm scope condition.
* Tách rule theo environment.
* Thêm suppression.
* Định nghĩa conflict policy.

## 24.3 Missing Owner

Nếu active rule không có owner:

```text
Đánh dấu Governance Risk
    ↓
Gán temporary owner
    ↓
Review trong SLA xác định
    ↓
Retire nếu không tìm được business owner
```

---

# 25. Business Process Swimlanes

## 25.1 New Rule Creation

```text
Requester        Rule Owner       Reviewer        QA             Approver        SRE
   |                 |               |              |                |             |
Submit Request       |               |              |                |             |
   |---------------> |               |              |                |             |
   |            Qualify             |              |                |             |
   |                 |----Design---->|              |                |             |
   |                 |               |---Review---> |                |             |
   |                 |               |              |---Test------>  |             |
   |                 |               |              |                |--Approve--> |
   |                 |               |              |                |             |--Publish-->
   |                 |               |              |                |             |
```

## 25.2 Rule Change

```text
Feedback
   ↓
Đánh giá false positive hoặc false negative
   ↓
Tạo version mới
   ↓
Review diff
   ↓
Regression test
   ↓
Approve
   ↓
Publish
   ↓
Monitor sau thay đổi
```

## 25.3 Rule Retirement

```text
Xác định stale rule
   ↓
Kiểm tra usage
   ↓
Tham vấn owner
   ↓
Deprecate
   ↓
Observe
   ↓
Disable
   ↓
Archive
```

---

# 26. Business Data Requirements

## 26.1 Rule Master Data

| Field | Mô tả |
|---|---|
| Rule ID | Mã định danh duy nhất |
| Rule Name | Tên rule |
| Description | Mục đích nghiệp vụ |
| Owner | Owner chịu trách nhiệm |
| Category | Nhóm rule |
| Severity | Severity mặc định |
| Status | Lifecycle state |
| Version | Phiên bản rule |
| Priority | Priority khi evaluation |
| Created By | Người tạo |
| Created Date | Thời điểm tạo |
| Approved By | Người approve |
| Approved Date | Thời điểm approve |
| Effective Date | Ngày active |
| Expiry Date | Ngày hết hiệu lực nếu có |
| Runbook Link | Hướng dẫn xử lý |
| Related System | Hệ thống liên quan |
| Related Screen | Màn hình liên quan |
| Related Incident | Incident hoặc RCA liên quan |

## 26.2 Rule Test Data

| Field | Mô tả |
|---|---|
| Test ID | Test case duy nhất |
| Rule ID | Rule liên quan |
| Rule Version | Version được test |
| Input Event | Dữ liệu đầu vào |
| Expected Result | Kết quả kỳ vọng |
| Actual Result | Kết quả thực tế |
| Status | Pass hoặc Fail |
| Tester | Người test |
| Test Date | Ngày test |
| Evidence | Screenshot, log hoặc report |

## 26.3 Rule Execution Data

| Field | Mô tả |
|---|---|
| Event ID | Event đầu vào |
| Rule ID | Rule match |
| Rule Version | Version được evaluate |
| Evaluation Result | Match, no match, suppressed, deduplicated |
| Severity | Severity cuối cùng |
| Evidence | Giải thích quyết định |
| Execution Time | Thời gian xử lý |
| Timestamp | Thời điểm evaluation |

---

# 27. KPIs and Success Metrics

## 27.1 Business KPIs

| KPI | Target Example |
|---|---|
| Alert Accuracy | Trên 95% alert hữu ích |
| False Positive Rate | Dưới 5% cho Critical |
| False Negative Rate | Giảm theo từng tháng |
| Mean Time To Detect | Giảm 30% |
| Mean Time To Create Rule | Dưới 3 business days |
| Mean Time To Approve Rule | Dưới 2 business days |
| Rule Owner Coverage | 100% |
| Runbook Coverage | 100% cho Major và Critical |
| Rule Review Compliance | 100% cho Critical rules theo quý |

## 27.2 Operational KPIs

| KPI | Target Example |
|---|---|
| Rule Evaluation Latency | Dưới 100ms trung bình |
| Alert Storm Events | Không có uncontrolled storm |
| Top Noisy Rule Count | Giảm theo tháng |
| Disabled Without Review | Không có |
| Production Rule Without Test | Không có |
| Rules Without Owner | Không có |

## 27.3 Product KPIs

| KPI | Ý nghĩa |
|---|---|
| Rule Reuse Rate | Tỷ lệ rule được xây từ template |
| Rule Template Coverage | Số lượng standard templates có sẵn |
| Rule Simulation Usage | Số rule author sử dụng simulator |
| Dry Run Adoption | Tỷ lệ high risk rules được dry run |
| Rule Feedback Completion | Tỷ lệ feedback được xử lý |

---

# 28. Best Practices

## 28.1 Rule Design Best Practices

* Thiết kế rule xoay quanh business impact.
* Tránh rule chỉ match keyword đơn lẻ.
* Ưu tiên structured fields thay vì raw text.
* Luôn định nghĩa scope.
* Luôn định nghĩa severity.
* Luôn định nghĩa owner.
* Luôn định nghĩa deduplication.
* Luôn định nghĩa evidence.
* Condition cần dễ hiểu.
* Dùng template cho pattern phổ biến.

## 28.2 Rule Governance Best Practices

* Không cho edit trực tiếp production rule.
* Sử dụng lifecycle states.
* Sử dụng versioning.
* Sử dụng approval workflow.
* Sử dụng audit trail.
* Review critical rules định kỳ.
* Retire stale rules.
* Hiển thị ownership rõ ràng.

## 28.3 Rule Testing Best Practices

* Test positive và negative cases.
* Test boundary values.
* Test suppression.
* Test deduplication.
* Chạy regression tests sau mỗi thay đổi.
* Dùng historical replay.
* Dùng dry run cho rule chưa chắc chắn.

## 28.4 Rule Monitoring Best Practices

* Theo dõi false positive và false negative.
* Theo dõi noisy rules.
* Theo dõi rule không có usage.
* Theo dõi feedback của operator.
* Theo dõi tỷ lệ alert chuyển thành incident.
* Review giá trị rule định kỳ.

## 28.5 Rule Authoring Best Practices

* Đặt tên rõ ràng.
* Mô tả theo ngôn ngữ nghiệp vụ.
* Liên kết runbook.
* Liên kết incident hoặc RCA liên quan.
* Tài liệu hóa ví dụ match.
* Tài liệu hóa ví dụ không match.
* Giải thích vì sao rule tồn tại.

---

# 29. Anti Patterns

## 29.1 Business Anti Patterns

| Anti Pattern | Risk |
|---|---|
| Tạo rule không có owner | Không ai bảo trì |
| Tạo rule không có action | Alert tạo noise |
| Approve rule không có test | Không biết hành vi production |
| Giữ rule lỗi thời | False alerts |
| Không có review cycle | Rule bị stale |
| Không có severity standard | Operation không nhất quán |
| Không có feedback loop | Accuracy không cải thiện |

## 29.2 Technical Anti Patterns

| Anti Pattern | Risk |
|---|---|
| Keyword only matching | False positive cao |
| Hardcoded rules | Khó thay đổi và governance kém |
| Không versioning | Không rollback được |
| Không evidence | Không giải thích được alert |
| Lạm dụng regex | Rule dễ vỡ |
| Không deduplication | Alert storm |
| Không suppression | Noise trong maintenance |
| Không có test dataset | Regression risk |

---

# 30. Example Business Scenarios

## 30.1 Scenario 1: New Critical CPU Rule

Business need:

```text
Production services trở nên không ổn định khi CPU trên 90% trong hơn 5 phút.
```

Rule request:

```text
Tạo Critical alert khi production CPU trên 90%.
```

Design decision:

* Scope là production only.
* Severity là Critical.
* Dedup key là service + env + alert type.
* Suppression là maintenance window.
* Evidence gồm OCR text, screenshot và extracted CPU value.
* Runbook là CPU high investigation.

Expected process:

```text
Submit → Qualify → Design → Review → Test → Approve → Publish → Monitor
```

## 30.2 Scenario 2: False Positive From Historical Chart

Issue:

```text
Rule detect CPU cao từ historical chart, không phải current status.
```

Root business problem:

```text
Rule chưa phân biệt current metric panel với historical chart region.
```

Process:

```text
Tạo rule change request
    ↓
Thêm screen region condition
    ↓
Replay historical events
    ↓
Approve version mới
    ↓
Publish
```

## 30.3 Scenario 3: Maintenance Window Suppression

Issue:

```text
Disk alert trigger trong planned backup.
```

Decision:

```text
Suppress disk usage warning trong approved backup window, nhưng không suppress Critical disk full alert.
```

Best practice:

* Suppression nên xét severity.
* Critical alert cần approval rõ ràng nếu muốn suppress.

## 30.4 Scenario 4: Retiring Obsolete Rule

Condition:

```text
Rule không có hit trong 180 ngày và dashboard liên quan đã được thay thế.
```

Process:

```text
Mark stale
    ↓
Confirm với owner
    ↓
Deprecate 30 ngày
    ↓
Disable
    ↓
Archive
```

## 30.5 Scenario 5: AI Suggested Rule

AI suggestion:

```text
Tạo alert khi text chứa replication delay.
```

Required governance:

```text
AI suggestion không được active tự động.
Rule phải đi qua qualification, design, review, test và approval.
```

Best practice:

* AI có thể hỗ trợ authoring.
* Human vẫn sở hữu quyết định và approval.
* AI suggestion phải có evidence và examples.

---

# 31. Business Requirements

## 31.1 Functional Business Requirements

| ID | Requirement |
|---|---|
| BPD-BR-001 | Hệ thống phải hỗ trợ rule request intake |
| BPD-BR-002 | Hệ thống phải hỗ trợ rule lifecycle states |
| BPD-BR-003 | Hệ thống phải hỗ trợ rule ownership |
| BPD-BR-004 | Hệ thống phải hỗ trợ rule versioning |
| BPD-BR-005 | Hệ thống phải hỗ trợ rule review |
| BPD-BR-006 | Hệ thống phải hỗ trợ rule approval |
| BPD-BR-007 | Hệ thống phải hỗ trợ rule testing evidence |
| BPD-BR-008 | Hệ thống phải hỗ trợ rule publication |
| BPD-BR-009 | Hệ thống phải hỗ trợ rule rollback |
| BPD-BR-010 | Hệ thống phải hỗ trợ rule retirement |
| BPD-BR-011 | Hệ thống phải hỗ trợ rule audit trail |
| BPD-BR-012 | Hệ thống phải hỗ trợ rule metrics |
| BPD-BR-013 | Hệ thống phải hỗ trợ false positive feedback |
| BPD-BR-014 | Hệ thống phải hỗ trợ false negative feedback |
| BPD-BR-015 | Hệ thống phải hỗ trợ rule catalog |
| BPD-BR-016 | Hệ thống phải hỗ trợ rule simulation |
| BPD-BR-017 | Hệ thống phải hỗ trợ dry run |
| BPD-BR-018 | Hệ thống phải hỗ trợ suppression policy |
| BPD-BR-019 | Hệ thống phải hỗ trợ deduplication policy |
| BPD-BR-020 | Hệ thống phải hỗ trợ evidence generation |

## 31.2 Non Functional Business Requirements

| ID | Requirement |
|---|---|
| BPD-NFR-001 | Rule change history phải auditable |
| BPD-NFR-002 | Production rule phải rollback capable |
| BPD-NFR-003 | Active rule phải có owner |
| BPD-NFR-004 | Major và Critical rule phải có runbook |
| BPD-NFR-005 | Rule approval phải traceable |
| BPD-NFR-006 | Rule testing phải repeatable |
| BPD-NFR-007 | Rule monitoring metrics phải available |
| BPD-NFR-008 | Rule governance phải hỗ trợ separation of duties |

---

# 32. Acceptance Criteria

Business Process Design cho Rule Engine được chấp nhận khi:

* End to end rule lifecycle được định nghĩa.
* RACI được định nghĩa.
* Rule intake process được định nghĩa.
* Rule design process được định nghĩa.
* Rule review process được định nghĩa.
* Rule testing process được định nghĩa.
* Rule approval process được định nghĩa.
* Rule publishing process được định nghĩa.
* Rule monitoring process được định nghĩa.
* Rule tuning process được định nghĩa.
* Rule retirement process được định nghĩa.
* Governance rules được định nghĩa.
* KPIs được định nghĩa.
* Có ví dụ cụ thể.
* Có best practices và anti patterns.
* Missing information được liệt kê rõ.

---

# 33. Implementation Recommendations

## 33.1 Phase 1: Manual Governance

Objective:

```text
Thiết lập rule lifecycle, ownership, templates và approval.
```

Deliverables:

* Rule request form.
* Rule design template.
* Rule test case template.
* Rule approval checklist.
* Rule catalog.
* Manual metrics report.

## 33.2 Phase 2: Tool Supported Process

Objective:

```text
Chuyển rule management vào workflow của ứng dụng.
```

Deliverables:

* Rule management UI.
* Rule simulator.
* Rule version history.
* Approval workflow.
* Audit trail.
* Test evidence storage.

## 33.3 Phase 3: Advanced Governance

Objective:

```text
Cải thiện accuracy, automation và governance.
```

Deliverables:

* Replay engine.
* Dry run mode.
* Impact analysis.
* Conflict detection.
* Rule dependency map.
* KPI dashboard.

## 33.4 Phase 4: AI Assisted Rule Management

Objective:

```text
Dùng AI để gợi ý cải tiến rule nhưng vẫn giữ human governance.
```

Deliverables:

* AI rule suggestion.
* False positive analysis.
* Rule recommendation.
* Similar rule detection.
* Rule documentation generation.

---

# 34. Missing Information

Để hoàn thiện tài liệu này cho triển khai thực tế, cần thu thập thêm:

* Event schema hiện tại của Screen Watcher.
* Quy trình alert và incident management hiện tại.
* Công cụ hiện tại như Jira, ServiceNow, Slack, Grafana hoặc Prometheus.
* Cơ cấu đội vận hành hiện tại.
* Approval workflow yêu cầu.
* Severity model đang dùng trong tổ chức.
* SLA cho alert response.
* Các ví dụ rule hiện có.
* Historical event và alert data.
* Maintenance window process.
* Security và compliance requirements.
* Có cần customer approval khi active rule không.
* Rule có được trigger automatic remediation không.
* Rule có được tạo ticket tự động không.
* AI suggestion có nằm trong scope không.

---

# 35. Knowledge Checklist

[ ] Hiểu rằng Rule Engine là một business capability, không chỉ là technical component.

[ ] Hiểu khác biệt giữa Event, Alert, Incident, Issue và Problem.

[ ] Hiểu full rule lifecycle từ request đến retirement.

[ ] Hiểu vì sao mỗi rule cần owner, version, test evidence và approval.

[ ] Hiểu vì sao alert quality phải được đo sau khi rule active.

[ ] Hiểu vì sao false positive và false negative feedback phải dẫn tới cải tiến rule.

[ ] Hiểu vì sao AI suggested rules vẫn cần human governance.

[ ] Hiểu cách RACI áp dụng vào rule management.

[ ] Hiểu suppression, deduplication và correlation ảnh hưởng thế nào tới alert quality.

[ ] Hiểu vì sao rule lỗi thời cần được retire.

---

# 36. Final Summary

Quy trình nghiệp vụ của Rule Engine phải chuyển hóa tri thức vận hành thành logic quyết định alert có kiểm soát và có thể đo lường.

Một quy trình Rule Engine trưởng thành không chỉ trả lời:

```text
Event này có nên trở thành alert không?
```

Nó còn phải trả lời:

```text
Vì sao event này nên trở thành alert?
Ai sở hữu logic này?
Ai đã phê duyệt?
Rule đã được kiểm thử như thế nào?
Rule có thể rollback không?
Làm sao biết rule vẫn còn hữu ích?
```

Operating model được khuyến nghị là:

```text
Governed Rule Lifecycle
+
Clear Ownership
+
Test Evidence
+
Approval Control
+
Production Monitoring
+
Continuous Improvement
```

Đây là nền tảng để xây dựng Rule Engine đủ tin cậy cho operation team và có thể mở rộng thành năng lực doanh nghiệp.
