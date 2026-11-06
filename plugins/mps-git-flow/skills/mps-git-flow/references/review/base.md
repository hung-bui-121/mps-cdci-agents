---
version: 1
---

# Quy tắc chung của team (lớp 1)

Áp dụng cho mọi file của mọi project. Đi kèm plugin nên chỉ có mức `major` và `minor`: các quy tắc này luôn là
cảnh báo, không bao giờ chặn commit. Chỉ quy tắc `blocker` do chính dự án khai báo trong `.mps/review.md` mới
chặn commit.

## BASE-HARDCODED-SECRET [major] Không ghi mật khẩu, khoá API, token hay khoá riêng vào code hoặc file cấu hình

Thông tin bí mật nằm trong git thì ai có quyền đọc repo cũng thấy, và không xoá được khỏi lịch sử. Bí mật phải
đọc từ biến môi trường, file cấu hình không commit (`.env`) hoặc kho bí mật của hệ thống build.

Sai:

```csharp
private const string ApiKey = "a1b2c3d4e5f6a7b8c9d0";
```

Đúng:

```csharp
private static string ApiKey => Environment.GetEnvironmentVariable("GAME_API_KEY");
```

## BASE-LOCAL-PATH [major] Không dùng đường dẫn tuyệt đối trên máy cá nhân hay địa chỉ localhost trong code chạy thật

Đường dẫn như `C:\Users\an\...` hay `/home/an/...` và địa chỉ `localhost` chỉ đúng trên máy người viết; trên máy
khác hoặc khi build sẽ hỏng. Dùng đường dẫn tương đối với project, hoặc lấy từ cấu hình.

Sai:

```python
DATA_DIR = "C:/Users/an/Desktop/data"
```

Đúng:

```python
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
```

## BASE-SWALLOWED-ERROR [major] Không bỏ qua lỗi một cách im lặng

Khối `catch` / `except` rỗng, hoặc bỏ qua kết quả lỗi, làm lỗi biến mất và rất khó tìm nguyên nhân sau này. Phải
xử lý lỗi, hoặc ít nhất ghi log kèm ngữ cảnh rồi báo tiếp.

Sai:

```csharp
try { SaveProgress(); } catch (Exception) { }
```

Đúng:

```csharp
try { SaveProgress(); }
catch (IOException e) { Debug.LogError($"Không lưu được tiến trình: {e.Message}"); throw; }
```

## BASE-DISABLED-CHECK [major] Không tắt hay comment bỏ test, kiểm tra dữ liệu hoặc kiểm tra bảo mật

Tắt kiểm tra chứng chỉ SSL, bỏ qua test, hay comment đoạn kiểm tra đầu vào để "cho chạy được" sẽ để lỗi thật lọt
ra ngoài. Sửa nguyên nhân, hoặc ghi rõ lý do và hỏi developer.

Sai:

```python
requests.get(url, verify=False)
```

Đúng:

```python
requests.get(url, verify=CA_BUNDLE_PATH)
```

## BASE-DEBUG-LEFTOVER [minor] Không để lại log gỡ lỗi, giá trị thử nghiệm hay khối code bị comment lớn

Dòng in ra để thử (`print`, `console.log`, `Debug.Log("test")`), giá trị cứng để test và các khối code cũ bị
comment làm code khó đọc và có thể lộ thông tin. Xoá trước khi commit.

Sai:

```javascript
console.log("DEBUG user", user);
const price = 0; // test tạm
```

Đúng:

```javascript
const price = product.price;
```

## BASE-NEW-TODO [minor] TODO / FIXME / HACK mới phải ghi rõ còn thiếu gì và vì sao

Một dòng `TODO` trống không giúp ai biết phải làm gì. Ghi rõ việc còn thiếu, lý do, và nếu có thì mã ticket.

Sai:

```csharp
// TODO
```

Đúng:

```csharp
// TODO: hỗ trợ tay cầm Bluetooth khi plugin input mới được duyệt (đang chờ ticket của team input)
```

## BASE-BUILD-ARTIFACT [minor] Không đưa file build, log, file tạm hay file của IDE vào thay đổi

File build (`.apk`, `.exe`, thư mục `Build/`), log, file tạm và cấu hình riêng của IDE (`.vs/`, `.idea/`) làm repo
nặng và gây xung đột cho người khác. Đây là nhận xét cho cả file, dùng dòng `-`.

Sai:

```text
Builds/game.apk
Logs/editor.log
.idea/workspace.xml
```

Đúng:

```text
# .gitignore
Builds/
Logs/
.idea/
```
