import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/features/planner/domain/planner_task.dart';

void main() {
  test('task survives JSON round trip', () {
    final PlannerTask task = PlannerTask.create(
      id: 'task-1',
      draft: TaskDraft(
        title: '  Купить продукты  ',
        note: '  Молоко и хлеб  ',
        date: DateTime(2026, 8, 2, 15),
        startMinute: 18 * 60 + 30,
        priority: TaskPriority.high,
      ),
      now: DateTime.utc(2026, 8, 1, 12),
    );

    final PlannerTask restored = PlannerTask.fromJson(task.toJson());

    expect(restored.id, task.id);
    expect(restored.title, 'Купить продукты');
    expect(restored.note, 'Молоко и хлеб');
    expect(restored.date, DateTime(2026, 8, 2));
    expect(restored.startMinute, 1110);
    expect(restored.durationMinutes, 60);
    expect(restored.priority, TaskPriority.high);
    expect(restored.createdAt, task.createdAt);
  });

  test('deadline survives JSON round trip', () {
    final PlannerTask task = PlannerTask.create(
      id: 'task-deadline',
      draft: TaskDraft(
        title: 'Отправить отчёт',
        date: DateTime(2026, 8, 7),
        deadlineDate: DateTime(2026, 8, 7, 23),
        deadlineMinute: 18 * 60,
        priority: TaskPriority.high,
      ),
      now: DateTime.utc(2026, 8, 1, 12),
    );

    final PlannerTask restored = PlannerTask.fromJson(task.toJson());

    expect(restored.deadlineDate, DateTime(2026, 8, 7));
    expect(restored.deadlineMinute, 1080);
    expect(restored.priority, TaskPriority.high);
  });

  test('editing a task can clear an existing deadline', () {
    final PlannerTask task = PlannerTask.create(
      id: 'task-clear-deadline',
      draft: TaskDraft(
        title: 'Отправить отчёт',
        date: DateTime(2026, 8, 7),
        deadlineDate: DateTime(2026, 8, 7),
        deadlineMinute: 18 * 60,
      ),
      now: DateTime.utc(2026, 8, 1, 12),
    );

    final PlannerTask updated = task.applyDraft(
      TaskDraft(title: task.title, date: task.date),
      DateTime.utc(2026, 8, 2, 12),
    );

    expect(updated.deadlineDate, isNull);
    expect(updated.deadlineMinute, isNull);
  });

  test('task draft rejects invalid input', () {
    expect(
      () => TaskDraft(title: '  ', date: DateTime(2026, 8, 2)),
      throwsArgumentError,
    );
    expect(
      () => TaskDraft(
        title: 'Task',
        date: DateTime(2026, 8, 2),
        startMinute: 1440,
      ),
      throwsArgumentError,
    );
  });

  test('JSON rejects impossible dates and unknown priorities', () {
    final Map<String, Object?> json = PlannerTask.create(
      id: 'task-1',
      draft: TaskDraft(title: 'Task', date: DateTime(2026, 8, 2)),
      now: DateTime.utc(2026, 8, 1),
    ).toJson();

    expect(
      () => PlannerTask.fromJson(<String, Object?>{
        ...json,
        'date': '2026-02-31',
      }),
      throwsFormatException,
    );
    expect(
      () => PlannerTask.fromJson(<String, Object?>{
        ...json,
        'priority': 'urgent',
      }),
      throwsFormatException,
    );
  });
}
