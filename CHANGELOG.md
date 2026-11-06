# Nhật ký thay đổi

Mỗi lần merge vào `main` phải tăng phiên bản (`VERSION` trong `mps.py` và `version` trong `plugin.json`, cùng một
giá trị) và thêm một mục ở đây. Mục mới nhất ở trên cùng.

## 0.1.1 - 2026-11-06
- Tự cài Git/Python còn thiếu khi bắt đầu (không hỏi trước, có báo một dòng). Mọi lần cài dùng chung một giới hạn
  thời gian (~500 giây); trình cài còn chạy quá giờ được báo `install_still_running` thay vì bắt tải tay. Chỉ yêu
  cầu khởi động lại Claude Code khi việc đó thật sự có tác dụng; ngược lại báo `git_not_on_path` hoặc
  `git_too_old`. Mục PATH trỏ tới ổ đĩa không tồn tại không còn làm script lỗi.
- Lệnh project setup + skill mps-project-setup để lead tích hợp plugin vào project (tự cập nhật mặc định); giữ
  nguyên kiểu thụt lề và xuống dòng của file, ghi file an toàn (atomic).
- env check báo khi có phiên bản plugin mới (plugin_outdated), trừ khi project ghim phiên bản bằng `ref`; báo khi
  project chưa tích hợp plugin (project_not_integrated). Việc kiểm tra phiên bản không bao giờ làm chậm quá 3 giây.
- File .env mới chỉ cần điền 3 dòng (MPS_JIRA_PAT, MPS_JIRA_PROJECT_KEY, MPS_GITLAB_PAT); trợ lý hướng dẫn từng
  bước (fill_guide), kể cả khi token bị từ chối (sai/hết hạn). Lỗi env_missing kèm `next: "env init --open"`.
- Commit và merge request không bao giờ có dòng ghi công AI: script tự gỡ đúng các dạng do AI thêm
  (`Co-Authored-By` có địa chỉ @anthropic.com hoặc chỉ ghi Claude / Claude Code / Claude <model>, "Generated
  with/by Claude Code", `Claude-Session:`, link phiên claude.ai), giữ nguyên đồng tác giả là người thật (kể cả
  người tên Claude) và mọi dòng khác; báo `attribution_removed`.
  `project setup` cũng thêm `"attribution": {"commit": "", "pr": "", "sessionUrl": false}` (không ghi đè giá trị
  project đã đặt).
- Merge request được giao cho chính người chạy (MR có sẵn người được giao thì giữ nguyên) và gắn nhãn
  `Enhancement` (story) / `Bug` (bug, hotfix) nếu nhãn đã có trên GitLab; không tự tạo nhãn. Lỗi giao / gắn nhãn
  chỉ là cảnh báo (`assign_failed`, `label_not_found`, `label_failed`), MR vẫn được tạo. Nhãn được tìm qua mọi
  trang kết quả (kể cả nhãn của group). MR xuất hiện trong lúc tạo (GitLab trả 409 hoặc 422) được dùng tiếp.
- Trình cài còn chạy quá giờ không còn giữ luồng xuất (stdout) của trợ lý: trên Windows winget được chạy tách
  hẳn qua cmd.exe (không kế thừa handle), trên macOS / Linux tiến trình con không giữ stdout; dòng JSON trả về
  ngay.

## 0.1.0
- Phiên bản đầu tiên.
