---
version: 1
ignore: [**/node_modules/**, **/dist/**, **/build/**, **/*.min.js, **/package-lock.json, **/yarn.lock, **/pnpm-lock.yaml]
---

# Quy tắc cho code web (lớp 2)

Tự áp dụng bên trong mỗi thư mục có `package.json`; đường dẫn tính từ thư mục đó. Thư mục thư viện, bản build và
file khoá phiên bản được bỏ qua. Chỉ có mức `major` và `minor`.

## WEB-UNSAFE-HTML [major] Không đưa dữ liệu không cố định vào innerHTML, dangerouslySetInnerHTML hay v-html
paths: **/*.js, **/*.jsx, **/*.ts, **/*.tsx, **/*.vue, **/*.svelte, **/*.html

HTML ghép từ dữ liệu người dùng hoặc từ server cho phép chèn script (XSS). Dùng `textContent`, binding văn bản của
framework, hoặc lọc HTML bằng thư viện đã được duyệt.

Sai:

```javascript
message.innerHTML = "<b>" + user.name + "</b>";
```

Đúng:

```javascript
const bold = document.createElement("b");
bold.textContent = user.name;
message.replaceChildren(bold);
```

## WEB-EVAL [major] Không dùng eval, new Function hay chuỗi code trong setTimeout / setInterval
paths: **/*.js, **/*.jsx, **/*.ts, **/*.tsx, **/*.vue, **/*.svelte, **/*.html

Các cách này chạy chuỗi như code: chậm, khó kiểm tra và mở đường cho chèn code. Truyền hàm thay cho chuỗi.

Sai:

```javascript
setTimeout("refresh()", 1000);
const fn = new Function("a", "b", "return a + b");
```

Đúng:

```javascript
setTimeout(refresh, 1000);
const fn = (a, b) => a + b;
```

## WEB-UNHANDLED-PROMISE [major] Promise và hàm async phải được await hoặc có xử lý lỗi
paths: **/*.js, **/*.jsx, **/*.ts, **/*.tsx, **/*.vue, **/*.svelte, **/*.html

Promise "thả nổi" làm lỗi mạng hoặc lỗi server biến mất, người dùng không được báo gì.

Sai:

```javascript
saveProfile(profile);
```

Đúng:

```javascript
try {
  await saveProfile(profile);
} catch (error) {
  showError("Không lưu được hồ sơ", error);
}
```

## WEB-LISTENER-LEAK [minor] Listener, interval và subscription do component thêm vào phải được gỡ khi dọn dẹp
paths: **/*.js, **/*.jsx, **/*.ts, **/*.tsx, **/*.vue, **/*.svelte, **/*.html

Không gỡ thì component đã đóng vẫn chạy code, gây rò rỉ bộ nhớ và lỗi khó tìm.

Sai:

```javascript
useEffect(() => {
  window.addEventListener("resize", onResize);
}, []);
```

Đúng:

```javascript
useEffect(() => {
  window.addEventListener("resize", onResize);
  return () => window.removeEventListener("resize", onResize);
}, []);
```

## WEB-LOOSE-EQUALITY [minor] Dùng === và !==, không dùng == và !=
paths: **/*.js, **/*.jsx, **/*.ts, **/*.tsx, **/*.vue, **/*.svelte, **/*.html

`==` tự đổi kiểu trước khi so sánh (`"0" == 0` là đúng), dễ gây lỗi bất ngờ.

Sai:

```javascript
if (count == "0") reset();
```

Đúng:

```javascript
if (count === 0) reset();
```
