---
version: 1
ignore: [**/*.unity, **/*.prefab, **/*.asset, **/*.meta, **/*.mat, **/*.anim, **/*.controller, ProjectSettings/**, Packages/packages-lock.json]
---

# Quy tắc cho project Unity C# (lớp 2)

Tự áp dụng bên trong mỗi thư mục project Unity (thư mục có `ProjectSettings/ProjectVersion.txt`); đường dẫn tính
từ thư mục đó. File Unity tự sinh dạng YAML (scene, prefab, asset, meta, material, animation) được bỏ qua: không
đáng gửi cho reviewer. Chỉ có mức `major` và `minor`.

## UNITY-NO-FIND-IN-UPDATE [major] Không gọi Find / FindObjectOfType / GetComponent trong Update, LateUpdate, FixedUpdate
paths: **/*.cs

Các hàm này tìm kiếm trong cả scene hoặc cả GameObject, chạy mỗi frame sẽ làm game giật trên điện thoại. Tìm một
lần trong `Awake` / `Start` và lưu vào biến.

Sai:

```csharp
void Update()
{
    var player = GameObject.Find("Player");
    player.GetComponent<Rigidbody>().AddForce(Vector3.up);
}
```

Đúng:

```csharp
private Rigidbody _playerBody;

void Awake() => _playerBody = GameObject.Find("Player").GetComponent<Rigidbody>();

void Update() => _playerBody.AddForce(Vector3.up);
```

## UNITY-NULL-CHECK-UNITY-OBJECT [major] Không dùng ?. / ?? / is null với UnityEngine.Object
paths: **/*.cs

Unity giữ object đã bị Destroy ở trạng thái "giả null": toán tử `==` của Unity biết điều đó, còn `?.`, `??` và
`is null` thì không, nên code vẫn chạy tiếp trên object đã huỷ. So sánh bằng `== null` hoặc dùng `if (obj)`.

Sai:

```csharp
_target?.TakeDamage(10);
var icon = customIcon ?? defaultIcon;
```

Đúng:

```csharp
if (_target != null) _target.TakeDamage(10);
var icon = customIcon != null ? customIcon : defaultIcon;
```

## UNITY-UNSUBSCRIBE-EVENTS [major] Sự kiện đăng ký trong OnEnable / Start phải được huỷ trong OnDisable / OnDestroy
paths: **/*.cs

Quên huỷ đăng ký làm object đã tắt hoặc đã huỷ vẫn nhận sự kiện, gây lỗi `MissingReferenceException` và rò rỉ bộ
nhớ.

Sai:

```csharp
void OnEnable() => GameEvents.ScoreChanged += OnScoreChanged;
```

Đúng:

```csharp
void OnEnable() => GameEvents.ScoreChanged += OnScoreChanged;
void OnDisable() => GameEvents.ScoreChanged -= OnScoreChanged;
```

## UNITY-EDITOR-API-IN-RUNTIME [major] Chỉ dùng API UnityEditor trong thư mục Editor hoặc trong #if UNITY_EDITOR
paths: **/*.cs

Namespace `UnityEditor` không có trong bản build: code chạy thật dùng nó sẽ làm build thất bại.

Sai:

```csharp
using UnityEditor;

public class Spawner : MonoBehaviour
{
    void Start() => AssetDatabase.Refresh();
}
```

Đúng:

```csharp
public class Spawner : MonoBehaviour
{
#if UNITY_EDITOR
    void OnValidate() => UnityEditor.EditorUtility.SetDirty(this);
#endif
}
```

## UNITY-NO-ALLOC-IN-UPDATE [minor] Không tạo rác (cấp phát bộ nhớ) mỗi frame trong vòng Update
paths: **/*.cs

`new List<>()`, LINQ, nối chuỗi và boxing trong `Update` tạo rác mỗi frame, làm bộ thu gom rác chạy thường xuyên
và game bị khựng. Tạo sẵn một lần rồi dùng lại.

Sai:

```csharp
void Update()
{
    var enemies = FindEnemies().Where(e => e.IsAlive).ToList();
    label.text = "Score: " + score;
}
```

Đúng:

```csharp
private readonly List<Enemy> _alive = new List<Enemy>();

void Update()
{
    CollectAlive(_alive);
    if (score != _shownScore) { _shownScore = score; label.SetText("Score: {0}", score); }
}
```

## UNITY-STRING-METHOD-NAME [minor] Không gọi hàm bằng tên dạng chuỗi (StartCoroutine, Invoke, SendMessage)
paths: **/*.cs

Đổi tên hàm thì chuỗi không đổi theo và lỗi chỉ lộ ra khi chạy. Truyền thẳng hàm, hoặc dùng `nameof`.

Sai:

```csharp
StartCoroutine("Respawn");
Invoke("Explode", 2f);
```

Đúng:

```csharp
StartCoroutine(Respawn());
Invoke(nameof(Explode), 2f);
```
