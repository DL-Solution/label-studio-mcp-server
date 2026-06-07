# v1.3.0 — LLM-assisted labeling via OpenRouter

## ✨ Нова можливість: розмітка обраною LLM через OpenRouter

Тепер анотації може генерувати **обрана LLM** (а не MCP-клієнт). Для кожної задачі сервер читає її дані + схему проєкту, шле strict-JSON запит у OpenRouter, конвертує відповідь у Label Studio `result` і зберігає його.

### 🛠 Нові інструменти
- **`label_task_with_llm_tool`** — розмітити одну задачу:
  `(task_id, model?, as_annotation?, extra_instructions?)`
- **`label_project_with_llm_tool`** — батч по проєкту:
  `(project_id, max_tasks=20, model?, as_annotation?, skip_already_predicted=True, extra_instructions?)`

За замовчуванням результат зберігається як **prediction** (ML pre-annotation); з `as_annotation=true` — як завершена анотація.

### 🧩 Підтримувані типи (текстові)
- **Choices** — класифікація (single/multiple)
- **Labels** — NER-спани (офсети обчислюються пошуком підрядка й **валідуються** проти тексту задачі перед збереженням)
- **TextArea** — вільний текст
- **Rating** — оцінка

Непідтримувані контролі (напр. bounding boxes на зображеннях) пропускаються з попередженням.

### ⚙️ Нові налаштування
| Налаштування | Опис |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter токен ([openrouter.ai/keys](https://openrouter.ai/keys)). Вмикає фічу; без нього інструменти неактивні. |
| `OPENROUTER_MODEL` | Модель за замовчуванням, напр. `openai/gpt-4o-mini` чи `google/gemini-2.0-flash`. Перевизначається у кожному виклику. |
| `OPENROUTER_BASE_URL` | База API (за потреби). Дефолт `https://openrouter.ai/api/v1`. |

У десктоп-розширенні ключ і модель задаються в **Settings** розширення.

### 📦 Без нових залежностей
OpenRouter викликається через `httpx` (вже в залежностях) — розмір бандла не зростає, нічого не компілюється.

## ✅ Перевірено
- 69 tools зареєстровано; обидва LLM-інструменти присутні.
- Тести: **40 passed** (офлайн-тести на витяг схеми, парсинг JSON, обчислення NER-офсетів, фільтрацію недозволених міток).
- Manifest валідний; бандл `label-studio-mcp-1.3.0.mcpb` пакується.

## 🚀 Приклад
> «Розміть задачу 123 моделлю `google/gemini-2.0-flash`»

Claude викличе `label_task_with_llm_tool`, і мітки створить саме обрана модель — як prediction у Label Studio.

**Full Changelog:** https://github.com/DL-Solution/label-studio-mcp-server/compare/v1.2.3...v1.3.0
