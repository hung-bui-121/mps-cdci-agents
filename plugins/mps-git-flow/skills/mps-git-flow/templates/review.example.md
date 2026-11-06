---
version: 1
# extends: unity-csharp      # thêm bộ quy tắc có sẵn (python, unity-csharp, web) khi plugin không tự nhận ra
# ignore: **/Assets/ThirdParty/**, Docs/**   # file không cần review code, cách nhau bằng dấu phẩy
---

# Quy tắc review code của dự án

File này do tech lead viết và commit qua merge request như mọi thay đổi khác. Trợ lý đọc file từ nhánh gốc trên
GitLab (develop, release/..., master), nên sửa file chỉ có hiệu lực sau khi được merge.

Mỗi quy tắc là một tiêu đề cấp 2 dạng `## MÃ-QUY-TẮC [mức] Tiêu đề`:
- Mã quy tắc: chữ IN HOA, số và dấu `-`; mỗi phần sau dấu `-` bắt đầu bằng chữ cái (ví dụ `SH-NO-SYNC-IO`, không
  được giống mã ticket Jira như `SH-12`).
- Mức: `blocker` (CHẶN commit cho tới khi code được sửa), `major` hoặc `minor` (chỉ cảnh báo, ghi vào merge
  request).
- Dòng đầu tiên sau tiêu đề có thể là `paths: **/Assets/Scripts/**/*.cs, Tools/*.cs` (mặc định: mọi file).
  Đường dẫn trong `paths:` và `ignore:` LUÔN tính từ gốc repo, kể cả khi project Unity nằm trong thư mục con
  (ví dụ `Client/Game/Assets/...`): viết `**/Assets/Scripts/**/*.cs` hoặc `Client/Game/Assets/Scripts/**/*.cs`,
  KHÔNG viết `Assets/Scripts/**/*.cs`. Quy tắc không khớp file nào sẽ bị cảnh báo `project_rule_matches_nothing`.
- File mà bộ quy tắc có sẵn bỏ qua (ví dụ `*.prefab`, `*.unity`, `.meta` của Unity) chỉ được review khi một quy
  tắc của dự án ghi rõ chúng trong `paths:` (ví dụ `paths: **/*.prefab`); quy tắc không có `paths:` thì không.
- Phần còn lại giải thích quy tắc, nên có ví dụ Sai / Đúng.
- Văn bản trước quy tắc đầu tiên (như đoạn này) không có tác dụng gì.

File sai định dạng thì CẢ file bị bỏ qua (chỉ còn quy tắc chung của team) và merge request ghi rõ điều đó.

Ví dụ (đang nằm trong khối code nên CHƯA có hiệu lực; chép ra ngoài khối, bỏ hai dòng ```` bao quanh để dùng):

````text
## SH-NO-SYNC-IO [blocker] Không đọc / ghi file đồng bộ trong code chạy mỗi frame
paths: **/Assets/Scripts/**/*.cs

Đọc file đồng bộ trong Update làm game đứng hình trên điện thoại. Dùng API bất đồng bộ hoặc đọc sẵn lúc load.

Sai:

```csharp
void Update() { var json = File.ReadAllText(path); }
```

Đúng:

```csharp
async void Start() { _json = await File.ReadAllTextAsync(path); }
```
````
