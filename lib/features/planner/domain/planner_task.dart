import '../../../core/date/calendar_date.dart';

enum TaskPriority {
  low,
  normal,
  high;

  String get label => switch (this) {
    TaskPriority.low => 'Низкий',
    TaskPriority.normal => 'Обычный',
    TaskPriority.high => 'Высокий',
  };
}

final class TaskDraft {
  TaskDraft({
    required String title,
    required DateTime date,
    String note = '',
    this.startMinute,
    int? durationMinutes,
    this.deadlineDate,
    this.deadlineMinute,
    this.priority = TaskPriority.normal,
    this.groupId,
  }) : title = _normalizeTitle(title),
       note = _normalizeNote(note),
       date = dateOnly(date),
       durationMinutes = startMinute == null ? null : (durationMinutes ?? 60) {
    _validateStartMinute(startMinute);
    _validateDuration(startMinute, this.durationMinutes);
    _validateDeadline(deadlineDate, deadlineMinute);
  }

  final String title;
  final String note;
  final DateTime date;
  final int? startMinute;
  final int? durationMinutes;
  final DateTime? deadlineDate;
  final int? deadlineMinute;
  final TaskPriority priority;
  final String? groupId;
}

final class PlannerTask {
  PlannerTask({
    required this.id,
    required String title,
    required DateTime date,
    required this.createdAt,
    required this.updatedAt,
    String note = '',
    this.startMinute,
    int? durationMinutes,
    DateTime? deadlineDate,
    this.deadlineMinute,
    this.priority = TaskPriority.normal,
    this.isCompleted = false,
    this.goalId,
    this.goalOccurrenceDate,
    this.completedAt,
    this.groupId,
  }) : title = _normalizeTitle(title),
       note = _normalizeNote(note),
       date = dateOnly(date),
       deadlineDate = deadlineDate == null ? null : dateOnly(deadlineDate),
       durationMinutes = startMinute == null ? null : (durationMinutes ?? 60) {
    if (id.trim().isEmpty) {
      throw ArgumentError.value(id, 'id', 'Task ID cannot be empty');
    }
    _validateStartMinute(startMinute);
    _validateDuration(startMinute, this.durationMinutes);
    _validateDeadline(this.deadlineDate, deadlineMinute);
    if ((goalId == null) != (goalOccurrenceDate == null)) {
      throw ArgumentError('goalId and goalOccurrenceDate must be set together');
    }
    if (isCompleted != (completedAt != null)) {
      throw ArgumentError('isCompleted and completedAt must be consistent');
    }
  }

  factory PlannerTask.create({
    required String id,
    required TaskDraft draft,
    required DateTime now,
  }) {
    final DateTime timestamp = now.toUtc();
    return PlannerTask(
      id: id,
      title: draft.title,
      note: draft.note,
      date: draft.date,
      startMinute: draft.startMinute,
      durationMinutes: draft.durationMinutes,
      deadlineDate: draft.deadlineDate,
      deadlineMinute: draft.deadlineMinute,
      priority: draft.priority,
      groupId: draft.groupId,
      createdAt: timestamp,
      updatedAt: timestamp,
    );
  }

  factory PlannerTask.fromJson(Map<String, Object?> json) {
    final Object? rawPriority = json['priority'];
    final TaskPriority priority;
    try {
      priority = TaskPriority.values.byName(rawPriority as String);
    } on Object {
      throw FormatException('Unknown task priority: $rawPriority');
    }

    return PlannerTask(
      id: json['id']! as String,
      title: json['title']! as String,
      note: (json['note'] as String?) ?? '',
      date: parseStorageDate(json['date']! as String),
      startMinute: json['startMinute'] as int?,
      durationMinutes: json['durationMinutes'] as int?,
      deadlineDate: json['deadlineDate'] == null
          ? null
          : parseStorageDate(json['deadlineDate']! as String),
      deadlineMinute: json['deadlineMinute'] as int?,
      priority: priority,
      isCompleted: (json['isCompleted'] as bool?) ?? false,
      goalId: json['goalId'] as String?,
      goalOccurrenceDate: json['goalOccurrenceDate'] == null
          ? null
          : parseStorageDate(json['goalOccurrenceDate']! as String),
      groupId: json['groupId'] as String?,
      completedAt: json['completedAt'] == null
          ? null
          : DateTime.parse(json['completedAt']! as String),
      createdAt: DateTime.parse(json['createdAt']! as String),
      updatedAt: DateTime.parse(json['updatedAt']! as String),
    );
  }

  final String id;
  final String title;
  final String note;
  final DateTime date;
  final int? startMinute;
  final int? durationMinutes;
  final DateTime? deadlineDate;
  final int? deadlineMinute;
  final TaskPriority priority;
  final bool isCompleted;
  final String? goalId;
  final DateTime? goalOccurrenceDate;
  final DateTime? completedAt;
  final String? groupId;
  final DateTime createdAt;
  final DateTime updatedAt;

  PlannerTask applyDraft(TaskDraft draft, DateTime now) {
    return PlannerTask(
      id: id,
      title: draft.title,
      note: draft.note,
      date: draft.date,
      startMinute: draft.startMinute,
      durationMinutes: draft.durationMinutes,
      deadlineDate: draft.deadlineDate,
      deadlineMinute: draft.deadlineMinute,
      priority: draft.priority,
      isCompleted: isCompleted,
      goalId: goalId,
      goalOccurrenceDate: goalOccurrenceDate,
      completedAt: completedAt,
      groupId: draft.groupId,
      createdAt: createdAt,
      updatedAt: now.toUtc(),
    );
  }

  PlannerTask toggleCompletion(DateTime now) {
    return PlannerTask(
      id: id,
      title: title,
      note: note,
      date: date,
      startMinute: startMinute,
      durationMinutes: durationMinutes,
      deadlineDate: deadlineDate,
      deadlineMinute: deadlineMinute,
      priority: priority,
      isCompleted: !isCompleted,
      goalId: goalId,
      goalOccurrenceDate: goalOccurrenceDate,
      completedAt: isCompleted ? null : now.toUtc(),
      groupId: groupId,
      createdAt: createdAt,
      updatedAt: now.toUtc(),
    );
  }

  PlannerTask withoutGroup() => PlannerTask(
    id: id,
    title: title,
    note: note,
    date: date,
    startMinute: startMinute,
    durationMinutes: durationMinutes,
    deadlineDate: deadlineDate,
    deadlineMinute: deadlineMinute,
    priority: priority,
    isCompleted: isCompleted,
    goalId: goalId,
    goalOccurrenceDate: goalOccurrenceDate,
    completedAt: completedAt,
    groupId: null,
    createdAt: createdAt,
    updatedAt: updatedAt,
  );
  TaskDraft toDraft() {
    return TaskDraft(
      title: title,
      note: note,
      date: date,
      startMinute: startMinute,
      durationMinutes: durationMinutes,
      deadlineDate: deadlineDate,
      deadlineMinute: deadlineMinute,
      priority: priority,
      groupId: groupId,
    );
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'id': id,
      'title': title,
      'note': note,
      'date': dateStorageKey(date),
      'startMinute': startMinute,
      'durationMinutes': durationMinutes,
      'deadlineDate': deadlineDate == null
          ? null
          : dateStorageKey(deadlineDate!),
      'deadlineMinute': deadlineMinute,
      'priority': priority.name,
      'isCompleted': isCompleted,
      'goalId': goalId,
      'goalOccurrenceDate': goalOccurrenceDate == null
          ? null
          : dateStorageKey(goalOccurrenceDate!),
      'completedAt': completedAt?.toUtc().toIso8601String(),
      'groupId': groupId,
      'createdAt': createdAt.toUtc().toIso8601String(),
      'updatedAt': updatedAt.toUtc().toIso8601String(),
    };
  }
}

String _normalizeTitle(String value) {
  final String normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, 'title', 'Task title cannot be empty');
  }
  if (normalized.length > 120) {
    throw ArgumentError.value(value, 'title', 'Task title is too long');
  }
  return normalized;
}

String _normalizeNote(String value) {
  final String normalized = value.trim();
  if (normalized.length > 1000) {
    throw ArgumentError.value(value, 'note', 'Task note is too long');
  }
  return normalized;
}

void _validateStartMinute(int? value) {
  if (value != null && (value < 0 || value > 1439)) {
    throw ArgumentError.value(
      value,
      'startMinute',
      'Expected a value from 0 to 1439',
    );
  }
}

void _validateDeadline(DateTime? deadlineDate, int? deadlineMinute) {
  if (deadlineMinute != null && deadlineDate == null) {
    throw ArgumentError('Время дедлайна требует дату дедлайна');
  }
  if (deadlineMinute != null && (deadlineMinute < 0 || deadlineMinute > 1439)) {
    throw ArgumentError.value(
      deadlineMinute,
      'deadlineMinute',
      'Expected a value from 0 to 1439',
    );
  }
}

void _validateDuration(int? startMinute, int? durationMinutes) {
  if (startMinute == null && durationMinutes != null) {
    throw ArgumentError('Длительность требует времени начала');
  }
  if (durationMinutes != null &&
      (durationMinutes < 15 ||
          durationMinutes > 1440 ||
          durationMinutes % 15 != 0 ||
          startMinute! + durationMinutes > 1440)) {
    throw ArgumentError(
      'Длительность должна идти шагом 15 минут и завершаться в тот же день',
    );
  }
}
