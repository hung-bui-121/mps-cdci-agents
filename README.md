# mps-cdci-agents

Bộ plugin Claude Code cho team MPS. Hiện có một plugin:

**mps-git-flow** - giúp bạn đưa code lên GitLab MPS (https://git-gst.mto.zing.vn) đúng quy trình ticket
Jira (https://jira-mps.mto.zing.vn), kể cả khi bạn không phải developer. Bạn chỉ cần nói với Claude kiểu
"đẩy code giúp mình", Claude sẽ:

1. Kiểm tra cấu hình và token (Jira, GitLab).
2. Hỏi mã ticket Jira, hoặc giúp bạn tạo ticket mới (Story hoặc Bug) giao cho chính bạn.
3. Hỏi giai đoạn: **dev**, **beta** hay **production**, và áp dụng đúng luật nhánh của team.
4. Đặt tên nhánh, nội dung commit, tiêu đề merge request (MR) theo chuẩn.
5. Kiểm tra an toàn: không cho commit file `.env`, token, khoá bí mật, file quá lớn.
6. Nhờ một trợ lý review xem các thay đổi có đúng phạm vi ticket không.
7. Tóm tắt mọi thứ và **chỉ commit + push khi bạn đồng ý**.
8. Tạo merge request, cập nhật trạng thái ticket Jira và gắn link MR vào ticket.

Plugin không bao giờ force push, không tự xoá nhánh, không merge MR và không đẩy thẳng vào `develop`, `master`
hay `release/*`. (MR được tạo với tuỳ chọn "xoá nhánh nguồn": GitLab tự xoá nhánh của ticket sau khi MR được
merge.)

## Cài đặt

Trong Claude Code, gõ:

```
/plugin marketplace add hung-bui-121/mps-cdci-agents
/plugin install mps-git-flow@mps-cdci-agents
```

Khởi động lại Claude Code nếu được yêu cầu.

Cần có: Git, và Python 3.8 trở lên (nếu máy chưa có Python, Claude sẽ hỏi bạn trước rồi cài giúp).

## Cấu hình file `.env` (mỗi project một file)

Cấu hình nằm trong file `.env` ở **thư mục gốc của project** bạn đang làm (không dùng cấu hình chung cho cả
máy). Lần đầu dùng, Claude sẽ tự tạo file này từ mẫu, tự thêm `.env` vào `.gitignore` và mở file cho bạn.

Bạn **tự điền token bằng trình soạn thảo** (Notepad, VS Code...). **Không dán token vào khung chat.**

| Khoá | Ý nghĩa |
|---|---|
| `MPS_JIRA_URL` | Địa chỉ Jira (mặc định `https://jira-mps.mto.zing.vn`) |
| `MPS_JIRA_PAT` | Token Jira: Jira > ảnh đại diện > Profile > Personal Access Tokens > Create token |
| `MPS_JIRA_PROJECT_KEY` | Mã project Jira (ví dụ `MPS`). Để trống thì Claude hỏi và tự điền |
| `MPS_GITLAB_URL` | Địa chỉ GitLab (mặc định `https://git-gst.mto.zing.vn`) |
| `MPS_GITLAB_PAT` | Token GitLab: ảnh đại diện > Edit profile > Access Tokens, chọn scope `api` và `write_repository` |
| `MPS_GITLAB_PROJECT` | Đường dẫn project dạng `group/project`. Để trống thì tự lấy từ `git remote origin` |
| `MPS_BRANCH_DEV` | Nhánh dev (mặc định `develop`) |
| `MPS_BRANCH_BETA_PREFIX` | Tiền tố nhánh beta (mặc định `release/`) |
| `MPS_BRANCH_PROD` | Nhánh production (mặc định `master`) |
| `MPS_CA_BUNDLE` | (Tuỳ chọn) đường dẫn file chứng chỉ CA nội bộ nếu gặp lỗi SSL |

Lưu ý: giá trị trong `.env` là nguồn duy nhất - biến môi trường của hệ điều hành không được dùng. Các khoá
đều có tiền tố `MPS_` để không đụng với `.env` riêng của ứng dụng.

Cần bật **VPN công ty** để kết nối Jira và GitLab.

## Cách dùng

Mở Claude Code trong thư mục project, rồi nói ví dụ:

- "Đẩy code giúp mình, ticket MPS-123"
- "Mình sửa xong lỗi đăng nhập, tạo MR giúp mình" (chưa có ticket - Claude sẽ giúp tạo)
- "Commit và push phần sửa lỗi này lên beta"

Luật nhánh tóm tắt:

| Giai đoạn | Loại ticket | Nhánh tạo từ | MR vào |
|---|---|---|---|
| dev | Story (`feature/...`), Bug (`bugfix/...`) | `develop` | `develop` |
| beta | chỉ Bug (`bugfix/...`) | nhánh `release/*` mới nhất | nhánh `release/*` đó |
| production | chỉ Bug (`hotfix/...`) - rủi ro cao, nên để developer làm | `master` | `master` |

Ví dụ: Story `MPS-123` "Thêm màn hình Đăng nhập bằng Google" -> nhánh
`feature/MPS-123-them-man-hinh-dang-nhap-bang-google`, commit `feat: MPS-123 Thêm màn hình Đăng nhập bằng Google`,
MR `MPS-123 Thêm màn hình Đăng nhập bằng Google` với mô tả `Close MPS-123`.

Chi tiết: [branch-rules.md](plugins/mps-git-flow/skills/mps-git-flow/references/branch-rules.md),
xử lý lỗi: [troubleshooting.md](plugins/mps-git-flow/skills/mps-git-flow/references/troubleshooting.md).

## Cấu trúc repo

```
.claude-plugin/marketplace.json            # marketplace "mps-cdci-agents"
plugins/mps-git-flow/
  .claude-plugin/plugin.json
  skills/mps-git-flow/
    SKILL.md                               # quy trình cho Claude
    scripts/mps.py                         # CLI Python (chỉ thư viện chuẩn), in ra JSON
    references/                            # luật nhánh, prompt review, cài Python, xử lý lỗi
    templates/env.example                  # mẫu file .env
tests/test_mps.py                          # unit test cho các hàm thuần
```

## Dành cho người phát triển plugin

Chạy test (Python 3; trên Windows `python` có thể là Python 2, hãy dùng `py -3`):

```
py -3 -m unittest discover -s tests -v
```

Thử CLI: `py -3 plugins/mps-git-flow/skills/mps-git-flow/scripts/mps.py --help`. Mỗi lệnh in đúng một object
JSON (`{"ok": true, ...}` hoặc `{"ok": false, "error": "...", "message": "..."}`). File `mps.py` phải luôn
parse được bằng Python 2.7 (không f-string, không annotation...) để báo lỗi "cần Python 3.8" một cách thân
thiện.
