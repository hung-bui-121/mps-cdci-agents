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
8. Tạo merge request, giao (assign) cho chính bạn và gắn nhãn theo loại ticket (Story -> `Enhancement`, Bug ->
   `Bug`); cập nhật trạng thái ticket Jira và gắn link MR vào ticket; cuối cùng liệt kê các file còn chưa commit.

Plugin không bao giờ force push, không tự xoá nhánh, không merge MR và không đẩy thẳng vào `develop`, `master`
hay `release/*`. (MR được tạo với tuỳ chọn "xoá nhánh nguồn": GitLab tự xoá nhánh của ticket sau khi MR được
merge.)

Commit và merge request **không bao giờ có dòng ghi công AI** (`Co-Authored-By: Claude ... <...@anthropic.com>`,
"Generated with/by Claude Code", `Claude-Session: ...`, link phiên `https://claude.ai/code/session...`): script tự
gỡ đúng các dòng đó; dòng đồng tác giả là người thật (kể cả người tên Claude) và các dòng khác nhắc tới claude
được giữ nguyên. Nhãn
`Enhancement` / `Bug` phải có sẵn trong project hoặc group trên GitLab: plugin không tự tạo nhãn mới; nếu chưa có,
Claude nhắc bạn nhờ lead tạo hoặc tự chọn nhãn trên trang MR. MR đã có người được giao thì giữ nguyên người đó.

## Cài đặt (thành viên)

Thường **không cần làm gì**: mở project trong Claude Code, bấm đồng ý ở hộp thoại "trust this folder" (tin cậy
thư mục), và plugin tự được cài nếu lead đã tích hợp plugin vào project (xem phần "Dành cho lead" bên dưới).
Plugin cũng tự cập nhật.

Lần đầu bạn nhờ Claude đẩy code, Claude tự kiểm tra máy và **tự cài Git / Python 3 nếu còn thiếu** (không hỏi
trước, chỉ báo một dòng). Có thể bạn sẽ thấy: trên Windows một hộp thoại hỏi quyền cài đặt (bấm Có / Yes); trên
Mac hộp thoại cài "Command Line Developer Tools" (bấm Install); trên Linux Claude đưa một lệnh có `sudo` để bạn
tự chạy trong Terminal (mật khẩu chỉ gõ trong Terminal, không gửi vào khung chat).

Lưu ý: Claude Code tải plugin từ GitHub bằng Git, nên máy cần có Git từ trước để plugin tự cài được (Claude Code
trên Windows vốn đã cần Git for Windows).

### Cài thủ công

Dùng khi project chưa được tích hợp, hoặc trên máy riêng của lead. Trong Claude Code, gõ:

```
/plugin marketplace add hung-bui-121/mps-cdci-agents
/plugin install mps-git-flow@mps-cdci-agents
```

Khởi động lại Claude Code nếu được yêu cầu.

## Cấu hình file `.env` (mỗi project một file)

Cấu hình nằm trong file `.env` ở **thư mục gốc của project** bạn đang làm (không dùng cấu hình chung cho cả
máy). Lần đầu dùng, Claude sẽ tự tạo file này từ mẫu, tự thêm `.env` vào `.gitignore`, mở file cho bạn và hướng
dẫn từng bước.

Bạn **tự điền token bằng trình soạn thảo** (Notepad, VS Code...). **Không dán token vào khung chat.**

### Bạn chỉ cần điền

| Khoá | Ý nghĩa |
|---|---|
| `MPS_JIRA_PAT` | Token Jira: Jira > ảnh đại diện > Profile > Personal Access Tokens > Create token |
| `MPS_JIRA_PROJECT_KEY` | Mã board Jira của team (ví dụ `MPS`) - hỏi lead nếu chưa biết, hoặc để trống để Claude gợi ý danh sách rồi tự điền |
| `MPS_GITLAB_PAT` | Token GitLab: ảnh đại diện > Edit profile > Access Tokens, chọn scope `api` và `write_repository` |

Các dòng còn lại trong `.env` đã có sẵn giá trị mặc định đúng, không cần sửa.

### Cấu hình nâng cao (thường không cần sửa)

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
| `MPS_GENERATED_PATTERNS` | (Tuỳ chọn, chỉ bạn tự sửa trong `.env`) thêm mẫu file do công cụ tự sửa, cách nhau bằng dấu phẩy, mỗi mẫu bắt đầu bằng tên thư mục/file cụ thể (ví dụ `Assets/Gen/**`, `yarn.lock`; mẫu như `*` bị bỏ qua). Trong project Unity (có `ProjectSettings/ProjectVersion.txt`) đã có sẵn các file Unity tự sửa (`ProjectSettings/**`, `Packages/packages-lock.json`, `UserSettings/**`, `Library/**`, `*.csproj`, `*.sln`). Chúng không ảnh hưởng việc chọn giai đoạn, nhưng vẫn được review và không tự động commit |

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
xử lý lỗi: [troubleshooting.md](plugins/mps-git-flow/skills/mps-git-flow/references/troubleshooting.md),
chuẩn bị môi trường (Git/Python): [setup-environment.md](plugins/mps-git-flow/skills/mps-git-flow/references/setup-environment.md).

## Dành cho lead: tích hợp plugin vào project

Làm một lần cho mỗi project để cả team tự có plugin (và các bản cập nhật):

1. Mở Claude Code trong project và nói **"tích hợp plugin vào project"** (skill `mps-project-setup`), hoặc tự chạy
   `py -3 <thư mục plugin>/skills/mps-git-flow/scripts/mps.py project setup`.
2. Lệnh này thêm vào `.claude/settings.json` của project (giữ nguyên mọi cấu hình khác) và đảm bảo `.env` nằm trong
   `.gitignore`. Nội dung được thêm:

   ```json
   {
     "extraKnownMarketplaces": {
       "mps-cdci-agents": {
         "source": {
           "source": "github",
           "repo": "hung-bui-121/mps-cdci-agents"
         },
         "autoUpdate": true
       }
     },
     "enabledPlugins": {
       "mps-git-flow@mps-cdci-agents": true
     },
     "attribution": {
       "commit": "",
       "pr": "",
       "sessionUrl": false
     }
   }
   ```

   `attribution` tắt dòng ghi công của Claude Code (`Co-Authored-By: Claude ...`, "Generated with Claude Code") trong
   commit và merge request của project. Nếu project đã tự đặt `attribution` thì giữ nguyên. Dù vậy, script vẫn tự gỡ
   các dòng ghi công AI khỏi mọi commit và MR mà nó tạo.

3. Commit các file này qua chính mps-git-flow (ticket + merge request), ví dụ ticket "Tích hợp plugin mps-git-flow
   vào project".

Thành viên sẽ thấy: khi mở project, Claude Code hỏi "trust this folder"; sau khi đồng ý, plugin tự được cài từ
GitHub. Lần đầu dùng, Claude tự cài Git/Python nếu thiếu (một dòng thông báo; có thể có hộp thoại Yes/No trên
Windows, hộp thoại Install trên Mac, hoặc một lệnh `sudo` để tự chạy trong Terminal trên Linux).

Kiểm tra: gõ `/plugin`, tab **Installed** có mps-git-flow kèm phiên bản; tab **Marketplaces** có mps-cdci-agents
với auto-update bật.

Muốn giữ cố định một phiên bản (không khuyến khích): thêm `"ref": "v0.1.1"` vào `source` của marketplace (cùng cấp
với `"repo"`). Mặc định là luôn theo bản mới nhất trên `main`. Khi đã ghim `ref`, skill không kiểm tra và không
nhắc cập nhật phiên bản mới nữa.

## Cập nhật plugin

- Trong project đã tích hợp, plugin **tự cập nhật**: Claude Code kiểm tra trong phiên làm việc (sau tin nhắn đầu
  tiên, trong khoảng 10 phút). Phiên đang chạy vẫn dùng bản cũ và báo "Run /reload-plugins to apply"; lần mở sau
  dùng bản mới.
- Xem phiên bản đang cài: `/plugin`, tab Installed.
- Cập nhật tay: gõ `/plugin marketplace update mps-cdci-agents` trong Claude Code (hoặc trong Terminal:
  `claude plugin marketplace update mps-cdci-agents` rồi `claude plugin update mps-git-flow@mps-cdci-agents`), sau
  đó gõ `/reload-plugins`.
- Mỗi lần chạy, skill cũng tự kiểm tra phiên bản mới và cập nhật giúp bạn (cảnh báo `plugin_outdated`), trừ khi
  project ghim phiên bản bằng `ref`.
- Các biến môi trường tắt cập nhật tự động: `DISABLE_UPDATES`, `DISABLE_AUTOUPDATER`,
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` (biến cuối cũng tắt luôn việc skill tự kiểm tra phiên bản).
  `FORCE_AUTOUPDATE_PLUGINS=1` bật lại cập nhật plugin.
- Bật/tắt auto-update trong màn hình `/plugin` sẽ ghi vào `.claude/settings.json` của project. Đừng commit thay đổi
  đó (review phạm vi sẽ để nó ngoài commit, trừ khi ticket nói về việc này).
- Máy đã cài bản 0.1.0 bằng tay cần cập nhật tay **một lần** để lên 0.1.1 (bản 0.1.0 chưa tự kiểm tra phiên bản).

## Phát hành phiên bản mới (người phát triển plugin)

1. Làm trên nhánh riêng; tăng `VERSION` trong `mps.py` và `version` trong `plugin.json` (cùng một giá trị: bản vá
   cho sửa lỗi/tài liệu, bản minor cho tính năng hoặc thay đổi quy trình) và thêm một mục vào `CHANGELOG.md`.
   Không ghi `version` trong `marketplace.json`.
2. Chạy `py -3 -m unittest discover -s tests -v` (test kiểm tra các phiên bản khớp nhau).
3. Khi thay đổi đụng tới cài đặt / cập nhật, chạy danh sách kiểm tra thủ công bên dưới và ghi kết quả vào MR.
4. Tạo MR vào `main`; tuỳ chọn gắn tag `v<phiên bản>` lên commit merge. Thành viên tự nhận bản mới.

Kiểm tra thủ công (máy thật, ngoài phần test tự động):

- Windows (PowerShell 5.1, tài khoản không phải admin nếu được): `bootstrap.ps1 -DetectOnly` khi có `py -3`; khi
  chỉ có lối tắt Microsoft Store (`store_stub_detected`, không bị treo); cài Python bằng winget phạm vi user (không
  hiện hộp thoại quyền, `installed: ["python"]` ngay trong lần chạy); không có winget (`winget_missing`); Git cũ
  (`winget upgrade`, rồi `restart_required` / `git_too_old` / `git_not_on_path` đúng trường hợp); proxy công ty /
  mất mạng (`install_failed`, vẫn in dòng JSON); đọc `message` tiếng Việt qua cả Git Bash và PowerShell.
- macOS: máy chưa có Command Line Tools (detect-only không mở hộp thoại); không có Homebrew (`xcode_clt_install`);
  có Homebrew (`brew install` không hỏi gì); chỉ có Python từ python.org; chạy `bootstrap.sh` trong Git Bash trên
  Windows (`use_powershell`).
- Linux (Ubuntu): không có sudo không mật khẩu (`run_in_terminal`); có sudo không mật khẩu hoặc root (cài xong,
  `ok: true`).
- Tích hợp và cập nhật: project mới có `.claude/settings.json` từ `project setup` -> mở Claude Code -> hộp thoại
  tin cậy -> plugin có trong `/plugin` với auto-update bật (ghi lại `autoUpdate` ở phạm vi project có được tôn trọng
  không); phát hành thử một bản mới qua một fork làm marketplace (`ref`) và xem thông báo cập nhật, `/reload-plugins`,
  `plugin_outdated` trong `env check`; bật/tắt auto-update trong `/plugin` có làm `.claude/settings.json` thay đổi
  không.
- `claude plugin update mps-git-flow@mps-cdci-agents` có chạy được với plugin được bật qua `enabledPlugins` ở phạm vi
  project (không cài thủ công) không.
- Thành viên mở Claude Code trong một thư mục con (ví dụ `Client/` của project Unity) có còn nhận
  `.claude/settings.json` ở gốc git không. (Tài liệu Claude Code hiện ghi rằng file này được đọc từ thư mục làm việc
  lúc mở Claude Code, nên nhiều khả năng là KHÔNG; khi đó hướng dẫn thành viên mở Claude Code ở gốc repo.)
- MR mới được giao cho người chạy và có nhãn `Enhancement` / `Bug` trên GitLab thật; project thiếu nhãn thì có cảnh
  báo `label_not_found` và vẫn tạo MR; commit / MR không còn dòng ghi công AI.

**Không tăng phiên bản thì không ai nhận được thay đổi.**

## Cấu trúc repo

```
.claude-plugin/marketplace.json            # marketplace "mps-cdci-agents"
.gitattributes                             # *.sh luôn LF, *.ps1 luôn CRLF
CHANGELOG.md                               # nhật ký thay đổi theo phiên bản
plugins/mps-git-flow/
  .claude-plugin/plugin.json               # phiên bản plugin (nguồn duy nhất)
  skills/mps-git-flow/
    SKILL.md                               # quy trình cho Claude
    scripts/mps.py                         # CLI Python (chỉ thư viện chuẩn), in ra JSON
    scripts/bootstrap.ps1                  # tự kiểm tra / cài Git + Python trên Windows
    scripts/bootstrap.sh                   # tự kiểm tra / cài Git + Python trên macOS / Linux
    references/                            # luật nhánh, prompt review, chuẩn bị môi trường (setup-environment.md), xử lý lỗi
    templates/env.example                  # mẫu file .env
  skills/mps-project-setup/
    SKILL.md                               # cho lead: tích hợp plugin vào project
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

`scripts/bootstrap.ps1` phải luôn là UTF-8 **có BOM** và chạy được trên Windows PowerShell 5.1 (không dùng cú
pháp của PowerShell 6+). `scripts/bootstrap.sh` phải là POSIX sh (không dùng tính năng riêng của bash), UTF-8
không BOM, xuống dòng LF. Test kiểm tra các điều này.
