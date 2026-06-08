# v1.1.0 — Config generation, analytics, resources & prompts

## ✨ Нові можливості

### 🛠 Tools
- **`generate_label_studio_label_config_tool`** — будує і **локально валідує** labeling-config XML з простого опису (`data_type` + `control_type` + `labels`). Більше не треба писати XML вручну. Підтримує:
  - текстову класифікацію (`Choices`, single/multiple)
  - NER / виділення спанів (`Labels`)
  - bounding boxes на зображеннях (`RectangleLabels`)
  - оцінки (`Rating`) і вільний текст (`TextArea`)
  - несумісні комбінації відхиляються з понятним повідомленням
- **`get_label_studio_project_statistics_tool`** — прогрес проєкту одним викликом: усього задач, розмічено, % завершення, лічильники annotations / predictions / ground-truth / skipped / finished.
- **`get_label_studio_annotator_statistics_tool`** — розподіл анотацій по анотаторах (вибірка, обмежена `max_tasks`; ground-truth по кожному).

### 📎 Resources (read-only контекст для клієнтів)
- `labelstudio://projects`
- `labelstudio://project/{id}/config`
- `labelstudio://project/{id}/summary`

### 💬 Prompts (готові сценарії)
- `setup_labeling_project` — створення проєкту з опису задачі
- `assess_annotation_quality` — аналіз прогресу та якості розмітки
- `generate_predictions_plan` — план додавання ML-предикшенів

## 🔍 Підсумок реєстру
**66 tools · 3 resources · 3 prompts**

## 📦 Артефакти
`label-studio-mcp-1.1.0.mcpb` (прикріплено до релізу)

**Full Changelog:** https://github.com/DL-Solution/label-studio-mcp-server/compare/v1.0.0...v1.1.0
