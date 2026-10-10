import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/features/planner/domain/planner_goal.dart';
import 'package:smart_planner/features/planner/domain/planner_task.dart';

void main() {
  PlannerGoal goal() => PlannerGoal(
    id: 'goal-1',
    title: 'Ходить в зал',
    note: '',
    startDate: DateTime(2026, 8, 1),
    endDate: DateTime(2026, 8, 7),
    intervalDays: 2,
    taskTitle: 'Тренировка',
    taskNote: '',
    taskStartMinute: 1080,
    taskPriority: TaskPriority.high,
    createdAt: DateTime.utc(2026, 8, 1),
    updatedAt: DateTime.utc(2026, 8, 1),
  );

  PlannerTask task(DateTime occurrence, {DateTime? completed}) => PlannerTask(
    id: 'task-${occurrence.day}',
    title: 'Тренировка',
    date: occurrence,
    goalId: 'goal-1',
    goalOccurrenceDate: occurrence,
    isCompleted: completed != null,
    completedAt: completed?.toUtc(),
    createdAt: DateTime.utc(2026, 8, 1),
    updatedAt: DateTime.utc(2026, 8, 1),
  );

  test('legacy goal JSON defaults timed task duration to one hour', () {
    final Map<String, Object?> legacy = goal().toJson()
      ..remove('taskDurationMinutes')
      ..remove('taskGroupId');
    final PlannerGoal restored = PlannerGoal.fromJson(legacy);
    expect(restored.taskDurationMinutes, 60);
    expect(restored.taskGroupId, isNull);
  });

  test('rejects default duration that would cross midnight', () {
    expect(
      () => GoalDraft(
        title: 'Поздняя цель',
        taskTitle: 'Поздняя задача',
        startDate: DateTime(2026, 8, 1),
        endDate: DateTime(2026, 8, 1),
        intervalDays: 1,
        taskStartMinute: 1410,
      ),
      throwsArgumentError,
    );
  });

  test('builds inclusive every-other-day schedule', () {
    expect(goal().occurrenceDates.map((DateTime date) => date.day), <int>[
      1,
      3,
      5,
      7,
    ]);
  });

  test('late completion counts but improves mood less than on-time', () {
    final PlannerGoal value = goal();
    final GoalProgress mixed = value.progress(<PlannerTask>[
      task(DateTime(2026, 8, 1), completed: DateTime(2026, 8, 1, 20)),
      task(DateTime(2026, 8, 3), completed: DateTime(2026, 8, 4, 10)),
      task(DateTime(2026, 8, 5)),
      task(DateTime(2026, 8, 7)),
    ], DateTime(2026, 8, 8));
    final GoalProgress allOnTime = value.progress(<PlannerTask>[
      for (final DateTime occurrence in value.occurrenceDates)
        task(occurrence, completed: occurrence.add(const Duration(hours: 20))),
    ], DateTime(2026, 8, 8));

    expect(mixed.completed, 2);
    expect(mixed.onTime, 1);
    expect(mixed.late, 1);
    expect(mixed.missed, 2);
    expect(mixed.completion, 0.5);
    expect(allOnTime.mood, greaterThan(mixed.mood));
    expect(allOnTime.emoji, '🤩');
  });

  test('deleted occurrence stays in total and becomes missed', () {
    final GoalProgress progress = goal().progress(
      <PlannerTask>[],
      DateTime(2026, 8, 8),
    );
    expect(progress.total, 4);
    expect(progress.completed, 0);
    expect(progress.missed, 4);
  });
}
