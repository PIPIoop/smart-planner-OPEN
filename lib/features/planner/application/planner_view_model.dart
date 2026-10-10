import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../../../core/date/calendar_date.dart';
import '../../../core/id/task_id_generator.dart';
import '../data/task_repository.dart';
import '../domain/calendar_month.dart';
import '../domain/planner_goal.dart';
import '../domain/planner_task.dart';
import '../domain/task_filter.dart';
import '../domain/task_group.dart';

enum PlannerLoadState { loading, ready, error }

final class PlannerViewModel extends ChangeNotifier {
  PlannerViewModel({
    required TaskRepository repository,
    required TaskIdGenerator idGenerator,
    DateTime? initialDate,
    DateTime Function()? now,
  }) : _repository = repository,
       _idGenerator = idGenerator,
       _now = now ?? DateTime.now {
    final DateTime seedDate = dateOnly(initialDate ?? _now());
    _selectedDate = seedDate;
    _displayedMonth = CalendarMonth(seedDate);
  }

  final TaskRepository _repository;
  final TaskIdGenerator _idGenerator;
  final DateTime Function() _now;

  List<PlannerTask> _tasks = <PlannerTask>[];
  List<PlannerGoal> _goals = <PlannerGoal>[];
  List<TaskGroup> _groups = <TaskGroup>[];
  PlannerLoadState _loadState = PlannerLoadState.loading;
  String? _errorMessage;
  late CalendarMonth _displayedMonth;
  late DateTime _selectedDate;
  String _searchQuery = '';
  TaskStatusFilter _statusFilter = TaskStatusFilter.all;
  bool _isSaving = false;
  bool _isSynchronizing = false;
  int _writeRevision = 0;

  PlannerLoadState get loadState => _loadState;
  String? get errorMessage => _errorMessage;
  CalendarMonth get displayedMonth => _displayedMonth;
  DateTime get selectedDate => _selectedDate;
  String get searchQuery => _searchQuery;
  TaskStatusFilter get statusFilter => _statusFilter;
  bool get isSaving => _isSaving;

  List<PlannerTask> get tasks => List<PlannerTask>.unmodifiable(_tasks);
  List<PlannerGoal> get goals => List<PlannerGoal>.unmodifiable(_goals);
  List<TaskGroup> get groups => List<TaskGroup>.unmodifiable(_groups);

  List<PlannerTask> get selectedDateTasks => tasksForDate(_selectedDate);

  int get displayedMonthTotalCount {
    return _tasks
        .where((PlannerTask task) => _displayedMonth.contains(task.date))
        .length;
  }

  int get displayedMonthCompletedCount {
    return _tasks.where((PlannerTask task) {
      return _displayedMonth.contains(task.date) && task.isCompleted;
    }).length;
  }

  Future<void> initialize() async {
    _loadState = PlannerLoadState.loading;
    _errorMessage = null;
    notifyListeners();

    try {
      _tasks = _sortTasks(await _repository.loadAll());
      _goals = await _repository.loadGoals();
      _groups = await _repository.loadGroups();
      _loadState = PlannerLoadState.ready;
    } on Object catch (error, stackTrace) {
      assert(() {
        debugPrint('Planner initialization failed: $error');
        debugPrintStack(stackTrace: stackTrace);
        return true;
      }());
      _loadState = PlannerLoadState.error;
      _errorMessage = 'Не удалось загрузить данные. Повторите попытку.';
    }

    notifyListeners();
  }

  Future<void> synchronize() async {
    if (_loadState != PlannerLoadState.ready || _isSaving || _isSynchronizing) {
      return;
    }

    _isSynchronizing = true;
    final int revisionAtStart = _writeRevision;

    try {
      final List<PlannerTask> synchronized = _sortTasks(
        await _repository.loadAll(),
      );
      final List<PlannerGoal> synchronizedGoals = await _repository.loadGoals();
      final List<TaskGroup> synchronizedGroups = await _repository.loadGroups();
      if (revisionAtStart != _writeRevision || _isSaving) {
        return;
      }
      if (!_sameTaskLists(_tasks, synchronized) ||
          !_sameGoalLists(_goals, synchronizedGoals) ||
          !_sameGroupLists(_groups, synchronizedGroups)) {
        _tasks = synchronized;
        _goals = synchronizedGoals;
        _groups = synchronizedGroups;
        notifyListeners();
      }
    } on Object catch (error, stackTrace) {
      assert(() {
        debugPrint('Planner background sync failed: $error');
        debugPrintStack(stackTrace: stackTrace);
        return true;
      }());
    } finally {
      _isSynchronizing = false;
    }
  }

  void selectDate(DateTime value) {
    _selectedDate = dateOnly(value);
    if (!_displayedMonth.contains(_selectedDate)) {
      _displayedMonth = CalendarMonth(_selectedDate);
    }
    notifyListeners();
  }

  void showPreviousMonth() {
    _displayedMonth = _displayedMonth.previous();
    _selectedDate = _displayedMonth.firstDay;
    notifyListeners();
  }

  void showNextMonth() {
    _displayedMonth = _displayedMonth.next();
    _selectedDate = _displayedMonth.firstDay;
    notifyListeners();
  }

  void showCurrentMonth() {
    final DateTime today = dateOnly(_now());
    _displayedMonth = CalendarMonth(today);
    _selectedDate = today;
    notifyListeners();
  }

  void setSearchQuery(String value) {
    final String normalized = value.trim().toLowerCase();
    if (_searchQuery == normalized) {
      return;
    }
    _searchQuery = normalized;
    notifyListeners();
  }

  void setStatusFilter(TaskStatusFilter value) {
    if (_statusFilter == value) {
      return;
    }
    _statusFilter = value;
    notifyListeners();
  }

  List<PlannerTask> tasksForDate(DateTime date) {
    return _sortTasks(
      _tasks
          .where((PlannerTask task) {
            return isSameDate(task.date, date) && _matchesFilters(task);
          })
          .toList(growable: false),
    );
  }

  GoalProgress goalProgress(PlannerGoal goal) => goal.progress(_tasks, _now());

  Future<void> createGoal(GoalDraft draft) async {
    final DateTime now = _now();
    final PlannerGoal goal = PlannerGoal.create(
      id: _idGenerator.next(),
      draft: draft,
      now: now,
    );
    final List<PlannerTask> generatedTasks = goal.occurrenceDates
        .map(
          (DateTime occurrence) => PlannerTask(
            id: _idGenerator.next(),
            title: goal.taskTitle,
            note: goal.taskNote,
            date: occurrence,
            startMinute: goal.taskStartMinute,
            durationMinutes: goal.taskDurationMinutes,
            priority: goal.taskPriority,
            groupId: goal.taskGroupId,
            goalId: goal.id,
            goalOccurrenceDate: occurrence,
            createdAt: now.toUtc(),
            updatedAt: now.toUtc(),
          ),
        )
        .toList(growable: false);

    await _persist(() => _repository.createGoal(goal, generatedTasks));
    _goals = <PlannerGoal>[..._goals, goal];
    _tasks = _sortTasks(<PlannerTask>[..._tasks, ...generatedTasks]);
    selectDate(goal.startDate);
  }

  Future<void> deleteGoal(String goalId) async {
    await _persist(() => _repository.deleteGoal(goalId));
    _goals = _goals
        .where((PlannerGoal goal) => goal.id != goalId)
        .toList(growable: false);
    _tasks = _tasks
        .where((PlannerTask task) => task.goalId != goalId)
        .toList(growable: false);
    notifyListeners();
  }

  TaskGroup? groupById(String? groupId) {
    if (groupId == null) return null;
    for (final TaskGroup group in _groups) {
      if (group.id == groupId) return group;
    }
    return null;
  }

  Future<void> createGroup(TaskGroupDraft draft) async {
    _ensureGroupColorAvailable(draft.colorHex);
    final TaskGroup group = TaskGroup.create(
      id: _idGenerator.next(),
      draft: draft,
      now: _now(),
    );
    final TaskGroup saved = await _persist(
      () => _repository.createGroup(group),
    );
    _groups = <TaskGroup>[..._groups, saved]
      ..sort((TaskGroup a, TaskGroup b) => a.name.compareTo(b.name));
    notifyListeners();
  }

  Future<void> updateGroup(String groupId, TaskGroupDraft draft) async {
    _ensureGroupColorAvailable(draft.colorHex, exceptId: groupId);
    final int index = _groups.indexWhere(
      (TaskGroup group) => group.id == groupId,
    );
    if (index == -1) throw StateError('Группа не найдена');
    final TaskGroup saved = await _persist(
      () => _repository.updateGroup(_groups[index].applyDraft(draft, _now())),
    );
    final List<TaskGroup> next = <TaskGroup>[..._groups];
    next[index] = saved;
    next.sort((TaskGroup a, TaskGroup b) => a.name.compareTo(b.name));
    _groups = next;
    notifyListeners();
  }

  void _ensureGroupColorAvailable(String colorHex, {String? exceptId}) {
    if (_groups.any(
      (TaskGroup group) => group.id != exceptId && group.colorHex == colorHex,
    )) {
      throw ArgumentError('Этот цвет уже используется другой группой');
    }
  }

  Future<void> deleteGroup(String groupId) async {
    await _persist(() => _repository.deleteGroup(groupId));
    _groups = _groups.where((TaskGroup group) => group.id != groupId).toList();
    _tasks = _tasks
        .map(
          (PlannerTask task) =>
              task.groupId == groupId ? task.withoutGroup() : task,
        )
        .toList();
    notifyListeners();
  }

  Future<void> createTask(TaskDraft draft) async {
    final PlannerTask task = PlannerTask.create(
      id: _idGenerator.next(),
      draft: draft,
      now: _now(),
    );
    final PlannerTask saved = await _persist(() => _repository.create(task));
    _tasks = _sortTasks(<PlannerTask>[..._tasks, saved]);
    selectDate(saved.date);
  }

  Future<void> updateTask(String taskId, TaskDraft draft) async {
    final int index = _findTaskIndex(taskId);
    final PlannerTask changed = _tasks[index].applyDraft(draft, _now());
    final PlannerTask saved = await _persist(() => _repository.update(changed));
    final List<PlannerTask> next = <PlannerTask>[..._tasks];
    next[index] = saved;
    _tasks = _sortTasks(next);
    selectDate(saved.date);
  }

  Future<void> toggleTaskCompletion(String taskId) async {
    final int index = _findTaskIndex(taskId);
    final PlannerTask changed = _tasks[index].toggleCompletion(_now());
    final PlannerTask saved = await _persist(() => _repository.update(changed));
    final List<PlannerTask> next = <PlannerTask>[..._tasks];
    next[index] = saved;
    _tasks = _sortTasks(next);
    notifyListeners();
  }

  Future<void> deleteTask(String taskId) async {
    final int index = _findTaskIndex(taskId);
    await _persist(() => _repository.delete(taskId));
    final List<PlannerTask> next = <PlannerTask>[..._tasks]..removeAt(index);
    _tasks = _sortTasks(next);
    notifyListeners();
  }

  Future<void> deleteAllTasks() async {
    await _persist(() => _repository.replaceAll(<PlannerTask>[]));
    _tasks = <PlannerTask>[];
    notifyListeners();
  }

  String exportJson() {
    return const JsonEncoder.withIndent('  ').convert(<String, Object?>{
      'schemaVersion': 2,
      'exportedAt': _now().toUtc().toIso8601String(),
      'tasks': _tasks
          .map((PlannerTask task) => task.toJson())
          .toList(growable: false),
      'goals': _goals
          .map((PlannerGoal goal) => goal.toJson())
          .toList(growable: false),
      'groups': _groups
          .map((TaskGroup group) => group.toJson())
          .toList(growable: false),
    });
  }

  Future<void> importJson(String raw, ImportMode mode) async {
    final Object? decoded = jsonDecode(raw);
    if (decoded is! Map<String, Object?>) {
      throw const FormatException(
        'Корневое значение должно быть объектом JSON',
      );
    }

    final Object? schemaVersion = decoded['schemaVersion'];
    if (schemaVersion != 1 && schemaVersion != 2) {
      throw FormatException('Неподдерживаемая версия схемы: $schemaVersion');
    }

    final List<PlannerTask> importedTasks = _decodeList(
      decoded['tasks'],
      field: 'tasks',
      itemName: 'задача',
      decode: PlannerTask.fromJson,
    );
    _ensureUniqueIds(importedTasks, (PlannerTask task) => task.id, 'задачи');

    // v1 intentionally contains only tasks; preserve the old import behavior.
    if (schemaVersion == 1) {
      final List<PlannerTask> next = switch (mode) {
        ImportMode.replace => importedTasks,
        ImportMode.merge => _mergeTasks(_tasks, importedTasks),
      };
      await _persist(() => _repository.replaceAll(_sortTasks(next)));
      _tasks = _sortTasks(next);
      notifyListeners();
      return;
    }

    final List<PlannerGoal> importedGoals = _decodeList(
      decoded['goals'],
      field: 'goals',
      itemName: 'цель',
      decode: PlannerGoal.fromJson,
    );
    final List<TaskGroup> importedGroups = _decodeList(
      decoded['groups'],
      field: 'groups',
      itemName: 'группа',
      decode: TaskGroup.fromJson,
    );
    _ensureUniqueIds(importedGoals, (PlannerGoal goal) => goal.id, 'цели');
    _ensureUniqueIds(importedGroups, (TaskGroup group) => group.id, 'группы');
    _ensureUniqueIds(
      importedGroups,
      (TaskGroup group) => group.colorHex,
      'цвета группы',
    );

    final List<PlannerTask> nextTasks = switch (mode) {
      ImportMode.replace => importedTasks,
      ImportMode.merge => _mergeTasks(_tasks, importedTasks),
    };
    final List<PlannerGoal> nextGoals = switch (mode) {
      ImportMode.replace => importedGoals,
      ImportMode.merge => _mergeByUpdatedAt(
        _goals,
        importedGoals,
        id: (PlannerGoal goal) => goal.id,
        updatedAt: (PlannerGoal goal) => goal.updatedAt,
      ),
    };
    final List<TaskGroup> nextGroups = switch (mode) {
      ImportMode.replace => importedGroups,
      ImportMode.merge => _mergeByUpdatedAt(
        _groups,
        importedGroups,
        id: (TaskGroup group) => group.id,
        updatedAt: (TaskGroup group) => group.updatedAt,
      ),
    };
    _ensureUniqueIds(
      nextGroups,
      (TaskGroup group) => group.colorHex,
      'цвета группы после объединения',
    );
    _validatePlannerReferences(nextTasks, nextGoals, nextGroups);

    await _persist(
      () => _repository.replacePlannerData(
        tasks: _sortTasks(nextTasks),
        goals: nextGoals,
        groups: nextGroups,
      ),
    );
    _tasks = _sortTasks(nextTasks);
    _goals = nextGoals;
    _groups = nextGroups;
    notifyListeners();
  }

  void clearError() {
    if (_errorMessage == null) {
      return;
    }
    _errorMessage = null;
    notifyListeners();
  }

  bool _matchesFilters(PlannerTask task) {
    final bool statusMatches = switch (_statusFilter) {
      TaskStatusFilter.all => true,
      TaskStatusFilter.active => !task.isCompleted,
      TaskStatusFilter.completed => task.isCompleted,
    };

    if (!statusMatches) {
      return false;
    }

    if (_searchQuery.isEmpty) {
      return true;
    }

    return task.title.toLowerCase().contains(_searchQuery) ||
        task.note.toLowerCase().contains(_searchQuery);
  }

  Future<T> _persist<T>(Future<T> Function() operation) async {
    if (_isSaving) {
      throw StateError('Дождитесь завершения предыдущего сохранения');
    }

    _isSaving = true;
    _writeRevision += 1;
    _errorMessage = null;
    notifyListeners();

    try {
      return await operation();
    } on Object catch (error, stackTrace) {
      assert(() {
        debugPrint('Planner save failed: $error');
        debugPrintStack(stackTrace: stackTrace);
        return true;
      }());
      _errorMessage = 'Не удалось сохранить данные. Повторите попытку.';
      rethrow;
    } finally {
      _isSaving = false;
      notifyListeners();
    }
  }

  int _findTaskIndex(String taskId) {
    final int index = _tasks.indexWhere(
      (PlannerTask task) => task.id == taskId,
    );
    if (index == -1) {
      throw StateError('Задача $taskId не найдена');
    }
    return index;
  }
}

bool _sameGoalLists(List<PlannerGoal> first, List<PlannerGoal> second) {
  return jsonEncode(first.map((PlannerGoal goal) => goal.toJson()).toList()) ==
      jsonEncode(second.map((PlannerGoal goal) => goal.toJson()).toList());
}

bool _sameGroupLists(List<TaskGroup> first, List<TaskGroup> second) {
  return jsonEncode(first.map((TaskGroup group) => group.toJson()).toList()) ==
      jsonEncode(second.map((TaskGroup group) => group.toJson()).toList());
}

bool _sameTaskLists(List<PlannerTask> first, List<PlannerTask> second) {
  if (first.length != second.length) {
    return false;
  }
  for (int index = 0; index < first.length; index += 1) {
    final PlannerTask left = first[index];
    final PlannerTask right = second[index];
    if (left.id != right.id ||
        left.title != right.title ||
        left.note != right.note ||
        left.date != right.date ||
        left.startMinute != right.startMinute ||
        left.durationMinutes != right.durationMinutes ||
        left.deadlineDate != right.deadlineDate ||
        left.deadlineMinute != right.deadlineMinute ||
        left.priority != right.priority ||
        left.isCompleted != right.isCompleted ||
        left.goalId != right.goalId ||
        left.goalOccurrenceDate != right.goalOccurrenceDate ||
        left.completedAt != right.completedAt ||
        left.groupId != right.groupId ||
        left.createdAt != right.createdAt ||
        left.updatedAt != right.updatedAt) {
      return false;
    }
  }
  return true;
}

List<T> _decodeList<T>(
  Object? raw, {
  required String field,
  required String itemName,
  required T Function(Map<String, Object?> json) decode,
}) {
  if (raw is! List<Object?>) {
    throw FormatException('Поле $field должно быть массивом');
  }
  return raw
      .map((Object? value) {
        if (value is! Map<String, Object?>) {
          throw FormatException(
            'Каждая сущность «$itemName» должна быть объектом',
          );
        }
        return decode(value);
      })
      .toList(growable: false);
}

void _ensureUniqueIds<T>(
  Iterable<T> items,
  String Function(T item) key,
  String label,
) {
  final Set<String> values = <String>{};
  for (final T item in items) {
    final String value = key(item);
    if (!values.add(value)) {
      throw FormatException('Повторяющееся значение $label: $value');
    }
  }
}

void _validatePlannerReferences(
  List<PlannerTask> tasks,
  List<PlannerGoal> goals,
  List<TaskGroup> groups,
) {
  final Set<String> goalIds = goals.map((PlannerGoal goal) => goal.id).toSet();
  final Set<String> groupIds = groups
      .map((TaskGroup group) => group.id)
      .toSet();
  for (final PlannerTask task in tasks) {
    if (task.goalId != null && !goalIds.contains(task.goalId)) {
      throw FormatException(
        'Задача ${task.id} ссылается на отсутствующую цель',
      );
    }
    if (task.groupId != null && !groupIds.contains(task.groupId)) {
      throw FormatException(
        'Задача ${task.id} ссылается на отсутствующую группу',
      );
    }
  }
  for (final PlannerGoal goal in goals) {
    if (goal.taskGroupId != null && !groupIds.contains(goal.taskGroupId)) {
      throw FormatException(
        'Цель ${goal.id} ссылается на отсутствующую группу',
      );
    }
    final Set<DateTime> allowed = goal.occurrenceDates.map(dateOnly).toSet();
    final Set<DateTime> actual = <DateTime>{};
    for (final PlannerTask task in tasks.where(
      (PlannerTask task) => task.goalId == goal.id,
    )) {
      final DateTime occurrence = dateOnly(task.goalOccurrenceDate!);
      if (!allowed.contains(occurrence)) {
        throw FormatException(
          'Задача ${task.id} имеет дату вне расписания цели ${goal.id}',
        );
      }
      if (!actual.add(occurrence)) {
        throw FormatException(
          'Цель ${goal.id} содержит повторяющуюся дату задачи',
        );
      }
    }
  }
}

List<T> _mergeByUpdatedAt<T>(
  List<T> current,
  List<T> imported, {
  required String Function(T item) id,
  required DateTime Function(T item) updatedAt,
}) {
  final Map<String, T> byId = <String, T>{
    for (final T item in current) id(item): item,
  };
  for (final T item in imported) {
    final T? existing = byId[id(item)];
    if (existing == null || updatedAt(item).isAfter(updatedAt(existing))) {
      byId[id(item)] = item;
    }
  }
  return byId.values.toList(growable: false);
}

List<PlannerTask> _sortTasks(Iterable<PlannerTask> tasks) {
  final List<PlannerTask> result = tasks.toList(growable: false);
  result.sort((PlannerTask first, PlannerTask second) {
    final int dateResult = compareCalendarDates(first.date, second.date);
    if (dateResult != 0) {
      return dateResult;
    }

    final int firstTime = first.startMinute ?? 1440;
    final int secondTime = second.startMinute ?? 1440;
    final int timeResult = firstTime.compareTo(secondTime);
    if (timeResult != 0) {
      return timeResult;
    }

    if (first.isCompleted != second.isCompleted) {
      return first.isCompleted ? 1 : -1;
    }

    return first.title.toLowerCase().compareTo(second.title.toLowerCase());
  });
  return result;
}

List<PlannerTask> _mergeTasks(
  List<PlannerTask> current,
  List<PlannerTask> imported,
) {
  final Map<String, PlannerTask> byId = <String, PlannerTask>{
    for (final PlannerTask task in current) task.id: task,
  };

  for (final PlannerTask task in imported) {
    final PlannerTask? existing = byId[task.id];
    if (existing == null || task.updatedAt.isAfter(existing.updatedAt)) {
      byId[task.id] = task;
    }
  }

  return _sortTasks(byId.values);
}
