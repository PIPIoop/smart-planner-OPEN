# Отчёт по входам и выходам

## Пользовательский интерфейс Flutter

| Узел | Вход | Выход |
|---|---|---|
| Календарь | дата и нажатие | `selectDate(date)` |
| Поиск/фильтр | строка, статус | отфильтрованный список |
| Диалог задачи | название, описание, дата, время, приоритет | `TaskDraft` |
| Диалог цели | название, обязательные начало/конец, шаг, шаблон задачи | `GoalDraft` и список повторений |
| Панель целей | задачи, `goalOccurrenceDate`, `completedAt`, текущая дата | прогресс, своевременность и смайлик |
| Checkbox | ID | атомарный `repository.update` |
| Экспорт | текущие задачи | JSON schema v1 |
| Импорт | JSON + merge/replace | проверенный `replaceAll` |
| Обучение | кнопки Далее/Назад/Готово | локальный UI-шаг, данные задач не меняются |

## Telegram

| Этап | Вход | Выход |
|---|---|---|
| Voice handler | Telegram OGG | временный файл, затем текст Whisper |
| Text handler | русский текст | `TaskExtraction` |
| TaskExtractor | текст + reference datetime + timezone | title/date/start/end/duration/confidence/warnings |
| ConfirmationStore | extraction + user/chat | токен на 15 минут |
| Кнопка «Да» | токен подтверждения | POST общей задачи; черновик удаляется только после успеха |
| Кнопка «Нет» | токен подтверждения | черновик удаляется без записи |

## TaskRepository Flutter

```dart
Future<List<PlannerTask>> loadAll();
Future<PlannerTask> create(PlannerTask task);
Future<PlannerTask> update(PlannerTask task);
Future<void> delete(String taskId);
Future<void> replaceAll(List<PlannerTask> tasks);
Future<List<PlannerGoal>> loadGoals();
Future<void> createGoal(PlannerGoal goal, List<PlannerTask> tasks);
Future<void> deleteGoal(String goalId);
```

`LocalTaskRepository` реализует контракт через SharedPreferences. `RemoteTaskRepository` использует REST. ViewModel меняет свой список только после успешного сохранения.

## Task API

| Endpoint | Вход | Успешный выход |
|---|---|---|
| `GET /health` | — | `{status, schemaVersion}` |
| `GET /api/v1/tasks` | — | JSON-массив задач |
| `POST /api/v1/tasks` | задача, метки времени необязательны | `201` + сохранённая задача |
| `PUT /api/v1/tasks/{id}` | полная задача с совпадающим ID | `200` + задача |
| `DELETE /api/v1/tasks/{id}` | ID | `204` |
| `PUT /api/v1/tasks` | `{tasks: [...]}` | атомарный `204` |
| `GET /api/v1/goals` | — | JSON-массив целей |
| `POST /api/v1/goals` | цель и точное расписание задач | `201` |
| `DELETE /api/v1/goals/{id}` | ID цели | атомарный `204` |

Ошибочные входы дают 4xx; недоступность сети преобразуется клиентами в контролируемую ошибку. CORS разрешён только для локальных origin.

## Общий JSON задачи

```json
{
  "id": "m123-abc",
  "title": "Подготовить отчёт",
  "note": "Проверить цифры",
  "date": "2026-08-03",
  "startMinute": 900,
  "priority": "high",
  "isCompleted": false,
  "goalId": null,
  "goalOccurrenceDate": null,
  "completedAt": null,
  "createdAt": "2026-08-02T17:00:00Z",
  "updatedAt": "2026-08-02T17:00:00Z"
}
```

`date` — календарная дата без timezone. Временные метки — UTC. `startMinute` равен 0…1439 либо 
null`. ID Telegram-запроса стабилен для одного подтверждения, поэтому повтор безопасен.

## Ошибки и атомарность

- невалидные дата, время, priority, длина и повторяющийся ID отклоняются до записи;
- SQLite использует параметры, транзакции и WAL;
- `replaceAll` не оставляет частично импортированное состояние;
- при ошибке Flutter сохраняет прежний UI-список;
- при ошибке Telegram API черновик не потребляется, пользователь может повторить;
- технические детали пишутся в debug/log, пользователю выводится безопасное сообщение.

## Группы и отчёты

| Узел | Вход | Выход |
|---|---|---|
| Менеджер групп | название + один свободный цвет палитры | `TaskGroup` |
| Форма задачи | необязательный ID одной группы | `TaskDraft.groupId` |
| `GET /api/v1/groups` | — | группы для Flutter и Telegram |
| Удаление группы | ID | задачи сохраняются с `groupId = null` |
| `/report` | кнопка «Неделя»/«Месяц» | HTML-caption + PNG 1200×820 |
| Report renderer | задачи, группы, период, локальное время | прогресс, своевременность, пропуски, распределение по группам |

## Telegram-секретарь

| Вход | Ответ без изменения данных | Изменение после подтверждения |
|---|---|---|
| `/today`, `/week` | расписание и рекомендации по накладкам/нагрузке | — |
| `/tasks` | список активных задач и карточка выбранной задачи | выполнить, перенести, сменить приоритет, удалить |
| `/free` | окна от 30 минут в 09:00–18:00 с буфером 15 минут | — |
| текст или голос | распознанный черновик и предупреждение о конфликте | создать задачу |
| `/settings` | текущие рабочие часы, буфер и длительность по умолчанию | — |

Любое обновление до обработчиков проверяется по `TELEGRAM_OWNER_USER_ID`; посторонний пользователь не может читать календарь или менять его.
Числовые диапазоны `с 10:00 до 12:00`, варианты `10 00` из распознавания речи и русские словесные часы/минуты преобразуются в одну задачу с `startMinute` и `durationMinutes`. Некорректный диапазон возвращает `intent=unknown`, предупреждение `invalid_time_range` и уточняющий вопрос.