---
version: 1
ignore: [**/__pycache__/**, **/*.pyc]
---

# Quy tắc cho code Python (lớp 2)

Tự áp dụng bên trong mỗi thư mục có `pyproject.toml`, `setup.py` hoặc `requirements*.txt`; đường dẫn tính từ thư
mục đó. Chỉ có mức `major` và `minor`.

## PY-BARE-EXCEPT [major] Không dùng except trống hoặc except Exception: pass
paths: **/*.py

`except:` bắt cả `KeyboardInterrupt` và lỗi lập trình, còn `pass` làm lỗi biến mất. Bắt đúng loại lỗi cần xử lý,
rồi xử lý hoặc ghi log.

Sai:

```python
try:
    data = load_config(path)
except:
    pass
```

Đúng:

```python
try:
    data = load_config(path)
except FileNotFoundError:
    logger.warning("Không có file cấu hình %s, dùng mặc định", path)
    data = DEFAULT_CONFIG
```

## PY-MUTABLE-DEFAULT [major] Không dùng giá trị mặc định có thể thay đổi cho tham số (list, dict, set)
paths: **/*.py

Giá trị mặc định chỉ được tạo một lần, nên mọi lần gọi dùng chung một list và dữ liệu bị lẫn giữa các lần gọi.

Sai:

```python
def add_item(item, items=[]):
    items.append(item)
    return items
```

Đúng:

```python
def add_item(item, items=None):
    items = [] if items is None else items
    items.append(item)
    return items
```

## PY-SHELL-INJECTION [major] Không chạy lệnh shell có ghép giá trị từ bên ngoài
paths: **/*.py

`shell=True` hoặc `os.system` với chuỗi có ghép giá trị cho phép chạy lệnh tuỳ ý nếu giá trị chứa ký tự đặc biệt.
Truyền danh sách tham số, không qua shell.

Sai:

```python
subprocess.run("convert " + user_file + " out.png", shell=True)
```

Đúng:

```python
subprocess.run(["convert", user_file, "out.png"], check=True)
```

## PY-UNSAFE-DESERIALIZE [major] Không dùng pickle.load, yaml.load không có SafeLoader hay eval với dữ liệu từ bên ngoài
paths: **/*.py

Các hàm này có thể chạy code tuỳ ý nằm trong dữ liệu. Dùng định dạng an toàn (`json`, `yaml.safe_load`).

Sai:

```python
settings = yaml.load(open(path))
value = eval(request_text)
```

Đúng:

```python
with open(path, encoding="utf-8") as handle:
    settings = yaml.safe_load(handle)
value = json.loads(request_text)
```

## PY-OPEN-WITHOUT-ENCODING [minor] Mở file văn bản phải ghi rõ encoding
paths: **/*.py

Không ghi `encoding=` thì Python dùng bảng mã mặc định của máy; trên Windows bảng mã khác macOS / Linux nên tiếng
Việt bị lỗi font.

Sai:

```python
with open("names.txt") as handle:
    names = handle.read()
```

Đúng:

```python
with open("names.txt", encoding="utf-8") as handle:
    names = handle.read()
```
