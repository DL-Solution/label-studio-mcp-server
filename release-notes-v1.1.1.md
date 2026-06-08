# v1.1.1 — Fix desktop-bundle install failure (Pillow build error)

## 🐛 Виправлення

Усунуто помилку встановлення `.mcpb`-розширення в Claude Desktop:

> The extension could not be installed due to the following error:
> `Failed to build pillow==11.2.1` → `Call to backend.build_wheel failed (exit status: 1)`

### Причина
Бандл запускається через `uv run`, тож `uv` сам обирає інтерпретатор Python на машині користувача — рантайм Claude тут не використовується. Без верхньої межі (`requires-python = ">=3.10"`) `uv` міг узяти **Python 3.14+**, для якого транзитивна залежність **Pillow** (тягнеться через `label-studio-sdk` разом із numpy/pandas/lxml) **не має готового wheel**. `uv` переходив на збірку з джерел, яка падає на машинах без C-тулчейну (типово — macOS без Xcode CLT).

Через це помилка відтворювалась на одних машинах і не відтворювалась на інших — залежно від того, який інтерпретатор обирав `uv`.

### Фікс
Обмежено підтримуваний діапазон Python до версій, що мають готові wheel-и, і закріплено це там, де воно реально потрапляє в бандл (`pyproject.toml` + `manifest.json`):
```toml
requires-python = ">=3.10,<3.14"
```
`uv` тепер гарантовано бере інтерпретатор 3.10–3.13 і ставить усі залежності з wheel-ів, без збірки.

### Перевірено
- `uv` обирає Python ≤ 3.13 (у тесті — `3.10.20`).
- Pillow 11.2.1 ставиться **з wheel**, без компіляції.
- Сервер імпортується; бандл пакується (`label-studio-mcp-1.1.1.mcpb`).

## 📦 Оновлення
Перевстановіть розширення новим бандлом `label-studio-mcp-1.1.1.mcpb` (нижче).

> Полагодити наявну інсталяцію без перевстановлення: створіть файл `.python-version` із вмістом `3.13` у теці розширення і перезапустіть Claude Desktop.

**Full Changelog:** https://github.com/DL-Solution/label-studio-mcp-server/compare/v1.1.0...v1.1.1
