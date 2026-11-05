# mps-cdci-agents

Bộ plugin Claude Code cho team MPS. Hiện có một plugin:

**mps-git-flow** - giúp bạn đưa code lên GitLab MPS (https://git-gst.mto.zing.vn) đúng quy trình ticket
Jira (https://jira-mps.mto.zing.vn), kể cả khi bạn không phải developer. Bạn chỉ cần nói với Claude kiểu
"đẩy code giúp mình", Claude sẽ:

1. Kiểm tra cấu hình và token (Jira, GitLab).
2. Hỏi mã ticket Jira - ở **board nào cũng được** (ví dụ `MPS-123`, hoặc `ART-12` của board team artist) - hoặc
   giúp bạn tạo ticket mới (Story hoặc Bug) giao cho chính bạn, trên board mặc định hoặc board khác bạn chọn.
3. Nhận biết giai đoạn từ nhánh bạn đang làm (**dev** = `develop`, **beta** = `release/*`, **production** =
   `master`) và áp dụng đúng luật nhánh: **làm từ nhánh nào thì merge về đúng nhánh đó**.
4. Đặt tên nhánh, nội dung commit, tiêu đề merge request (MR) theo chuẩn.
5. Kiểm tra an toàn: không cho commit file `.env`, token, khoá bí mật, file quá lớn.
6. Nhờ một trợ lý review xem các thay đổi có đúng phạm vi ticket không. **Chỉ những file thật sự làm cho ticket
   mới được commit**; file ngoài phạm vi (ví dụ Unity tự sửa `ProjectSettings`/`.meta`, file lock, thay đổi của
   người khác) được giữ nguyên trên máy, không commit - để không ảnh hưởng người khác.
7. Tóm tắt mọi thứ (danh sách "Sẽ commit" và "Không commit") và **chỉ commit + push khi bạn đồng ý**.
8. Tạo merge request, cập nhật trạng thái ticket Jira và gắn link MR vào ticket; cuối cùng liệt kê các file còn
   chưa commit.

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
| `MPS_JIRA_PROJECT_KEY` | Mã project Jira (board) mặc định khi tạo ticket mới (ví dụ `MPS`). Bắt buộc; để trống thì Claude hỏi và tự điền. Có thể khác project GitLab |
| `MPS_GITLAB_URL` | Địa chỉ GitLab (mặc định `https://git-gst.mto.zing.vn`) |
| `MPS_GITLAB_PAT` | Token GitLab: ảnh đại diện > Edit profile > Access Tokens, chọn scope `api` và `write_repository` |
| `MPS_GITLAB_PROJECT` | Đường dẫn project dạng `group/project`. Để trống thì tự lấy từ `git remote origin` |
| `MPS_BRANCH_DEV` | Nhánh dev (mặc định `develop`) |
| `MPS_BRANCH_BETA_PREFIX` | Tiền tố nhánh beta (mặc định `release/`) |
| `MPS_BRANCH_PROD` | Nhánh production (mặc định `master`) |
| `MPS_CA_BUNDLE` | (Tuỳ chọn) đường dẫn file chứng chỉ CA nội bộ nếu gặp lỗi SSL |
| `MPS_GENERATED_PATTERNS` | (Tuỳ chọn) thêm mẫu file do công cụ tự sửa, cách nhau bằng dấu phẩy (ví dụ `Assets/Gen/**`). Mặc định đã có các file Unity tự sửa (`ProjectSettings/**`, `Packages/packages-lock.json`, `UserSettings/**`, `*.csproj`, `*.sln`, `Library/**`). Chúng không ảnh hưởng việc chọn giai đoạn, nhưng vẫn được review và không tự động commit |

Lưu ý: giá trị trong `.env` là nguồn duy nhất - biến môi trường của hệ điều hành không được dùng. Các khoá
đều có tiền tố `MPS_` để không đụng với `.env` riêng của ứng dụng.

Cần bật **VPN công ty** để kết nối Jira và GitLab.

## Cách dùng

Mở Claude Code trong thư mục project, rồi nói ví dụ:

- "Đẩy code giúp mình, ticket MPS-123"
- "Đẩy giúp mình phần icon mới, ticket ART-12" (ticket của board artist)
- "Mình sửa xong lỗi đăng nhập, tạo MR giúp mình" (chưa có ticket - Claude sẽ giúp tạo)
- "Commit và push phần sửa lỗi này lên beta"

Luật nhánh tóm tắt (làm từ nhánh nào thì merge về đúng nhánh đó):

| Giai đoạn | Loại ticket | Nhánh tạo từ | MR vào |
|---|---|---|---|
| dev | Story (`feature/...`), Bug (`bugfix/...`) | `develop` | `develop` |
| beta | chỉ Bug (`bugfix/...`) | nhánh `release/*` bạn đang làm (nếu chưa ở nhánh nào thì nhánh mới nhất) | đúng nhánh `release/*` đó |
| production | chỉ Bug (`hotfix/...`) - rủi ro cao, nên để developer làm | `master` | `master` |

Nếu bạn đang có thay đổi trên `release/1.1` thì thay đổi sẽ vào `release/1.1` (Claude sẽ nhắc nếu đó không phải
nhánh beta mới nhất). Nếu bạn đã sửa code trên một nhánh mà lại chọn giai đoạn khác, Claude sẽ dừng lại và giải
thích - việc chuyển thay đổi sang giai đoạn khác cần developer. Khi chưa sửa gì, Claude hỏi bạn giai đoạn.

Claude chỉ commit đúng những file đã qua review phạm vi; nếu bạn sửa thêm sau khi review, Claude sẽ review lại.

Ví dụ: Story `MPS-123` "Thêm màn hình Đăng nhập bằng Google" -> nhánh
`feature/MPS-123-them-man-hinh-dang-nhap-bang-google`, commit `feat: MPS-123 Thêm màn hình Đăng nhập bằng Google`,
MR `MPS-123 Thêm màn hình Đăng nhập bằng Google` với mô tả `Close MPS-123`. Ticket của board khác cũng vậy:
`ART-12` "Vẽ lại icon nhân vật" -> nhánh `feature/ART-12-ve-lai-icon-nhan-vat`, mô tả MR `Close ART-12` (GitLab tự
liên kết với mọi project trên cùng Jira).

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
tests/test_mps.py                          # unit test (hàm thuần) + test git chạy offline với origin cục bộ
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
