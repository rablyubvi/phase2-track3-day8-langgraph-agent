# Day 08 Lab Report

## 1. Team / student

- Tên: Trần Ngô Hồng Hà
- Repo/commit: https://github.com/rablyubvi/phase2-track3-day8-langgraph-agent
- Ngày: 11/05/2026

## 2. Architecture 

Graph đi theo chuỗi `START -> intake -> classify -> ... -> finalize -> END`.

- `intake`: chuẩn hoá query, ghi audit event, phát hiện sơ bộ email/phone.
- `classify`: phân loại theo độ ưu tiên keyword: `risky` -> `tool` -> `missing_info` -> `error` -> `simple`.
- `tool -> evaluate`: tạo vòng retry có giới hạn.
- `risky_action -> approval -> tool`: bắt buộc bước phê duyệt trước khi đi tiếp.
- `clarify`: trả câu hỏi làm rõ khi thiếu thông tin.
- `dead_letter`: xử lý khi retry vượt `max_attempts`.
- `finalize`: chốt trạng thái và ghi event kết thúc.

State dùng reducer append-only cho `messages`, `tool_results`, `errors`, `events`; các trường còn lại là overwrite để giữ state gọn và dễ serialize.

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| `messages` | append | lưu lịch sử xử lý/audit |
| `tool_results` | append | giữ kết quả tool qua các lần retry |
| `errors` | append | ghi nhận lỗi/transient failure |
| `events` | append | phục vụ metrics và trace |
| `route` | overwrite | chỉ cần route hiện tại |
| `risk_level` | overwrite | phản ánh kết quả classify mới nhất |
| `attempt` | overwrite | đếm số lần retry hiện tại |
| `final_answer` | overwrite | câu trả lời cuối cùng |
| `pending_question` | overwrite | câu hỏi làm rõ hiện tại |
| `proposed_action` | overwrite | đề xuất risky action hiện tại |
| `approval` | overwrite | trạng thái phê duyệt hiện tại |
| `evaluation_result` | overwrite | kết quả đánh giá lần gần nhất |

## 4. Scenario results

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | yes | 0 | 0 |
| S02_tool | tool | tool | yes | 0 | 0 |
| S03_missing | missing_info | missing_info | yes | 0 | 0 |
| S04_risky | risky | risky | yes | 0 | 1 |
| S05_error | error | error | yes | 2 | 0 |
| S06_delete | risky | risky | yes | 0 | 1 |
| S07_dead_letter | error | simple | no | 0 | 0 |

Tổng quan từ `outputs/metrics.json`:

- Tổng scenario: 7
- Success rate: 85.71%
- Trung bình nodes visited: 6.29
- Tổng retries: 2
- Tổng interrupts: 2

## 5. Failure analysis

1. Retry/tool failure:
   - Nhánh `error` tạo lỗi giả ở `tool_node`, sau đó `evaluate_node` phát hiện kết quả bắt đầu bằng `ERROR` và đi vào `retry`.
   - Vòng lặp được chặn bởi `max_attempts`, tránh chạy vô hạn.

2. Risky action không có phê duyệt:
   - Nhánh `risky` luôn đi qua `approval`.
   - Nếu `approval` bị từ chối, router có thể đưa về `clarify` hoặc hướng xử lý an toàn khác.

3. Trường hợp S07:
   - Scenario này cho thấy một edge case chưa khớp kỳ vọng: query được classify thành `simple` thay vì `error`.
   - Nguyên nhân là heuristic hiện tại ưu tiên keyword và chưa đủ mạnh để suy luận lỗi hệ thống khi câu query mang tính mô tả dài.

## 6. Persistence / recovery evidence

Graph hỗ trợ `thread_id` ổn định theo từng scenario để phục vụ checkpoint và replay.

- `build_checkpointer("memory")` dùng `MemorySaver()` cho chạy cục bộ.
- `build_checkpointer("sqlite")` dùng `SqliteSaver(conn=sqlite3.connect(...))` với WAL mode.
- Mỗi run truyền `configurable.thread_id = thread_id` để checkpoint bám đúng luồng.

Trong lần chạy hiện tại, `resume_success = false` vì chưa thực hiện crash-resume đầy đủ.

## 7. Extension work

- Có hỗ trợ SQLite checkpointer.
- Có event/audit log trong state để phục vụ metrics.
- Có branch approval/HITL bằng `LANGGRAPH_INTERRUPT=true`.

## 8. Improvement plan

Ưu tiên tiếp theo:

1. Làm router classify tốt hơn để xử lý các query dài nhưng vẫn thuộc nhánh `error`.
2. Thêm test cho hidden edge cases và approval reject path.
3. Bổ sung crash-resume thật với SQLite checkpoint và ghi bằng chứng vào report.
