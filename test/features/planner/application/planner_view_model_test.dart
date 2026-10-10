import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/core/id/task_id_generator.dart';
import 'package:smart_planner/features/planner/application/planner_view_model.dart';
import 'package:smart_planner/features/planner/domain/planner_goal.dart';
import 'package:smart_planner/features/planner/domain/planner_task.dart';
import 'package:smart_planner/features/planner/domain/task_group.dart';
import 'package:smart_planner/features/planner/domain/task_filter.dart';

import '../../../support/fake_task_repository.dart';

void main() {
  late FakeTaskRepository repository;
  late PlannerViewModel viewModel;
  final DateTime fixedNow = DateTime.utc(2026, 8, 2, 10);

  setUp(() {
    repository = FakeTaskRepository();
    viewModel = PlannerViewModel(
      repository: repository,
      idGenerator: TaskIdGenerator(random: Random(1)),
      initialDate: DateTime(2026, 8, 2),
      now: () => fixedNow,
    );
  });

  tearDown(() => viewModel.dispose());

  test('supports create, update, complete and delete lifecycle', () async {
    await viewModel.initialize();

    await viewModel.createTask(
      TaskDraft(title: 'Задача', date: DateTime(2026, 8, 2)),
    );

    expect(viewModel.tasks, hasLength(1));
    final PlannerTask created = viewModel.tasks.single;

    await viewModel.updateTask(
      created.id,
      TaskDraft(
        title: 'Новая задача',
        date: DateTime(2026, 8, 3),
        priority: TaskPriority.high,
      ),
    );
    expect(viewModel.tasks.single.title, 'Новая задача');
    expect(viewModel.selectedDate, DateTime(2026, 8, 3));

    await viewModel.toggleTaskCompletion(created.id);
    expect(viewModel.tasks.single.isCompleted, isTrue);

    await viewModel.deleteTask(created.id);
    expect(viewModel.tasks, isEmpty);
    expect(repository.stored, isEmpty);
  });

  test('filters selected day by status and search', () async {
    await viewModel.initialize();
    await viewModel.createTask(
      TaskDraft(title: 'Купить хлеб', date: DateTime(2026, 8, 2)),
    );
    await viewModel.createTask(
      TaskDraft(title: 'Позвонить врачу', date: DateTime(2026, 8, 2)),
    );
    await viewModel.toggleTaskCompletion(viewModel.tasks.first.id);

    viewModel.setStatusFilter(TaskStatusFilter.active);
    expect(viewModel.selectedDateTasks, hasLength(1));

    viewModel.setStatusFilter(TaskStatusFilter.all);
    viewModel.setSearchQuery('врач');
    expect(viewModel.selectedDateTasks.single.title, 'Позвонить врачу');
  });

  test('backup v2 restores tasks goals groups and goal template', () async {
    await viewModel.initialize();
    await viewModel.createGroup(
      TaskGroupDraft(name: 'Здоровье', colorHex: '#14B8A6'),
    );
    final String groupId = viewModel.groups.single.id;
    await viewModel.createGoal(
      GoalDraft(
        title: 'Ходить в зал',
        taskTitle: 'Тренировка',
        startDate: DateTime(2026, 8, 2),
        endDate: DateTime(2026, 8, 4),
        intervalDays: 2,
        taskStartMinute: 600,
        taskDurationMinutes: 90,
        taskGroupId: groupId,
      ),
    );

    final Map<String, Object?> decoded =
        jsonDecode(viewModel.exportJson())! as Map<String, Object?>;
    expect(decoded['schemaVersion'], 2);
    expect(decoded['tasks'], hasLength(2));
    expect(decoded['goals'], hasLength(1));
    expect(decoded['groups'], hasLength(1));

    final FakeTaskRepository restoredRepository = FakeTaskRepository();
    final PlannerViewModel restored = PlannerViewModel(
      repository: restoredRepository,
      idGenerator: TaskIdGenerator(random: Random(2)),
      initialDate: DateTime(2026, 8, 2),
      now: () => fixedNow,
    );
    addTearDown(restored.dispose);
    await restored.initialize();
    await restored.importJson(jsonEncode(decoded), ImportMode.replace);

    expect(restored.groups.single.name, 'Здоровье');
    expect(restored.goals.single.taskDurationMinutes, 90);
    expect(restored.goals.single.taskGroupId, groupId);
    expect(
      restored.tasks.map((PlannerTask task) => task.durationMinutes),
      everyElement(90),
    );
    expect(
      restored.tasks.map((PlannerTask task) => task.groupId),
      everyElement(groupId),
    );
  });

  test('legacy backup v1 still imports tasks only', () async {
    await viewModel.initialize();
    await viewModel.createGroup(
      TaskGroupDraft(name: 'Работа', colorHex: '#3B82F6'),
    );
    final PlannerTask legacyTask = PlannerTask(
      id: 'legacy-task',
      title: 'Из старой копии',
      date: DateTime(2026, 8, 5),
      createdAt: fixedNow,
      updatedAt: fixedNow,
    );
    await viewModel.importJson(
      jsonEncode(<String, Object?>{
        'schemaVersion': 1,
        'tasks': <Object?>[legacyTask.toJson()],
      }),
      ImportMode.replace,
    );

    expect(viewModel.tasks.single.id, 'legacy-task');
    expect(viewModel.groups.single.name, 'Работа');
  });

  test('rejects damaged JSON and duplicate task IDs atomically', () async {
    await viewModel.initialize();
    await viewModel.createTask(
      TaskDraft(title: 'Исходная задача', date: DateTime(2026, 8, 2)),
    );
    final Map<String, Object?> exported =
        jsonDecode(viewModel.exportJson())! as Map<String, Object?>;
    final List<Object?> tasks = exported['tasks']! as List<Object?>;
    final String duplicateTasks = jsonEncode(<String, Object?>{
      ...exported,
      'tasks': <Object?>[...tasks, tasks.single],
    });

    await expectLater(
      viewModel.importJson('{broken', ImportMode.replace),
      throwsFormatException,
    );
    await expectLater(
      viewModel.importJson(duplicateTasks, ImportMode.replace),
      throwsFormatException,
    );
    expect(viewModel.tasks.single.title, 'Исходная задача');
    expect(repository.stored.single.title, 'Исходная задача');
  });

  test('backup v2 rejects unknown references before saving', () async {
    await viewModel.initialize();
    await viewModel.createTask(
      TaskDraft(title: 'Исходная', date: DateTime(2026, 8, 2)),
    );
    final Map<String, Object?> backup =
        jsonDecode(viewModel.exportJson())! as Map<String, Object?>;
    final List<Object?> tasks = backup['tasks']! as List<Object?>;
    final Map<String, Object?> task = Map<String, Object?>.from(
      tasks.single! as Map<String, Object?>,
    )..['groupId'] = 'missing-group';

    await expectLater(
      viewModel.importJson(
        jsonEncode(<String, Object?>{
          ...backup,
          'tasks': <Object?>[task],
        }),
        ImportMode.replace,
      ),
      throwsFormatException,
    );
    expect(repository.stored.single.title, 'Исходная');
    expect(repository.groups, isEmpty);
  });

  test('keeps previous state when repository save fails', () async {
    await viewModel.initialize();
    repository.saveError = StateError('disk unavailable');

    await expectLater(
      viewModel.createTask(
        TaskDraft(title: 'Не сохранится', date: DateTime(2026, 8, 2)),
      ),
      throwsStateError,
    );
    expect(viewModel.tasks, isEmpty);
    expect(
      viewModel.errorMessage,
      'Не удалось сохранить данные. Повторите попытку.',
    );
    expect(viewModel.isSaving, isFalse);
  });
  test('background sync applies tasks created by another client', () async {
    await viewModel.initialize();
    final PlannerTask external = PlannerTask(
      id: 'telegram-task',
      title: 'Создано через Telegram',
      date: DateTime(2026, 8, 2),
      createdAt: fixedNow,
      updatedAt: fixedNow,
    );
    repository.stored = <PlannerTask>[external];

    await viewModel.synchronize();

    expect(viewModel.tasks.single.id, 'telegram-task');
  });

  test('stale background response cannot overwrite a local write', () async {
    await viewModel.initialize();
    final Completer<List<PlannerTask>> delayed = Completer<List<PlannerTask>>();
    repository.nextLoad = delayed;

    final Future<void> synchronization = viewModel.synchronize();
    await Future<void>.delayed(Duration.zero);
    await viewModel.createTask(
      TaskDraft(title: 'Локальная задача', date: DateTime(2026, 8, 2)),
    );
    delayed.complete(<PlannerTask>[]);
    await synchronization;

    expect(viewModel.tasks.single.title, 'Локальная задача');
  });
  test('creates a goal and all linked task occurrences atomically', () async {
    await viewModel.initialize();
    await viewModel.createGoal(
      GoalDraft(
        title: 'Месяц ходить в зал',
        taskTitle: 'Тренировка',
        startDate: DateTime(2026, 8, 2),
        endDate: DateTime(2026, 8, 8),
        intervalDays: 2,
      ),
    );

    expect(viewModel.goals, hasLength(1));
    expect(viewModel.tasks, hasLength(4));
    expect(
      viewModel.tasks.every(
        (PlannerTask task) => task.goalId == viewModel.goals.single.id,
      ),
      isTrue,
    );
    expect(repository.goals, hasLength(1));
    expect(repository.stored, hasLength(4));
  });
  test('creates, assigns, edits and deletes a task group safely', () async {
    await viewModel.initialize();
    await viewModel.createGroup(
      TaskGroupDraft(name: 'Работа', colorHex: '#3B82F6'),
    );
    final TaskGroup group = viewModel.groups.single;
    await expectLater(
      viewModel.createGroup(
        TaskGroupDraft(name: 'Другая', colorHex: '#3B82F6'),
      ),
      throwsArgumentError,
    );
    await viewModel.createTask(
      TaskDraft(title: 'Отчёт', date: DateTime(2026, 8, 2), groupId: group.id),
    );
    expect(viewModel.tasks.single.groupId, group.id);

    await viewModel.updateGroup(
      group.id,
      TaskGroupDraft(name: 'Проекты', colorHex: '#14B8A6'),
    );
    expect(viewModel.groups.single.name, 'Проекты');
    expect(viewModel.groups.single.colorHex, '#14B8A6');

    await viewModel.deleteGroup(group.id);
    expect(viewModel.groups, isEmpty);
    expect(viewModel.tasks.single.groupId, isNull);
    expect(repository.stored.single.groupId, isNull);
  });
}
