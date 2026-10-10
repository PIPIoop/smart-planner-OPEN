import '../../../core/date/calendar_date.dart';
import 'planner_task.dart';

final class GoalDraft {
  GoalDraft({
    required String title,
    required String taskTitle,
    required DateTime startDate,
    required DateTime endDate,
    required this.intervalDays,
    String note = '',
    String taskNote = '',
    this.taskStartMinute,
    int? taskDurationMinutes,
    this.taskPriority = TaskPriority.normal,
    this.taskGroupId,
  }) : title = title.trim(),
       taskTitle = taskTitle.trim(),
       note = note.trim(),
       taskNote = taskNote.trim(),
       taskDurationMinutes = _normalizeGoalDuration(
         taskStartMinute,
         taskDurationMinutes,
       ),
       startDate = dateOnly(startDate),
       endDate = dateOnly(endDate) {
    if (this.title.isEmpty || this.title.length > 120) {
      throw ArgumentError('Название цели должно содержать 1–120 символов');
    }
    if (this.taskTitle.isEmpty || this.taskTitle.length > 120) {
      throw ArgumentError('Название задачи должно содержать 1–120 символов');
    }
    if (this.endDate.isBefore(this.startDate)) {
      throw ArgumentError('Конечная дата не может быть раньше начальной');
    }
    if (intervalDays < 1 || intervalDays > 365) {
      throw ArgumentError('Период должен быть от 1 до 365 дней');
    }
    final int occurrenceCount =
        endDate.difference(startDate).inDays ~/ intervalDays + 1;
    if (occurrenceCount > 1000) {
      throw ArgumentError('Цель не может содержать больше 1000 повторений');
    }
    if (this.note.length > 1000 || this.taskNote.length > 1000) {
      throw ArgumentError('Описание не может быть длиннее 1000 символов');
    }
  }

  final String title;
  final String note;
  final DateTime startDate;
  final DateTime endDate;
  final int intervalDays;
  final String taskTitle;
  final String taskNote;
  final int? taskStartMinute;
  final int? taskDurationMinutes;
  final TaskPriority taskPriority;
  final String? taskGroupId;
}

final class PlannerGoal {
  PlannerGoal({
    required this.id,
    required this.title,
    required this.note,
    required DateTime startDate,
    required DateTime endDate,
    required this.intervalDays,
    required this.taskTitle,
    required this.taskNote,
    required this.taskStartMinute,
    int? taskDurationMinutes,
    required this.taskPriority,
    this.taskGroupId,
    required this.createdAt,
    required this.updatedAt,
  }) : taskDurationMinutes = _normalizeGoalDuration(
         taskStartMinute,
         taskDurationMinutes,
       ),
       startDate = dateOnly(startDate),
       endDate = dateOnly(endDate);

  factory PlannerGoal.create({
    required String id,
    required GoalDraft draft,
    required DateTime now,
  }) {
    final DateTime timestamp = now.toUtc();
    return PlannerGoal(
      id: id,
      title: draft.title,
      note: draft.note,
      startDate: draft.startDate,
      endDate: draft.endDate,
      intervalDays: draft.intervalDays,
      taskTitle: draft.taskTitle,
      taskNote: draft.taskNote,
      taskStartMinute: draft.taskStartMinute,
      taskDurationMinutes: draft.taskDurationMinutes,
      taskPriority: draft.taskPriority,
      taskGroupId: draft.taskGroupId,
      createdAt: timestamp,
      updatedAt: timestamp,
    );
  }

  factory PlannerGoal.fromJson(Map<String, Object?> json) => PlannerGoal(
    id: json['id']! as String,
    title: json['title']! as String,
    note: (json['note'] as String?) ?? '',
    startDate: parseStorageDate(json['startDate']! as String),
    endDate: parseStorageDate(json['endDate']! as String),
    intervalDays: json['intervalDays']! as int,
    taskTitle: json['taskTitle']! as String,
    taskNote: (json['taskNote'] as String?) ?? '',
    taskStartMinute: json['taskStartMinute'] as int?,
    taskDurationMinutes: json['taskStartMinute'] == null
        ? null
        : (json['taskDurationMinutes'] as int? ?? 60),
    taskPriority: TaskPriority.values.byName(json['taskPriority']! as String),
    taskGroupId: json['taskGroupId'] as String?,
    createdAt: DateTime.parse(json['createdAt']! as String),
    updatedAt: DateTime.parse(json['updatedAt']! as String),
  );

  final String id;
  final String title;
  final String note;
  final DateTime startDate;
  final DateTime endDate;
  final int intervalDays;
  final String taskTitle;
  final String taskNote;
  final int? taskStartMinute;
  final int? taskDurationMinutes;
  final TaskPriority taskPriority;
  final String? taskGroupId;
  final DateTime createdAt;
  final DateTime updatedAt;

  List<DateTime> get occurrenceDates {
    final List<DateTime> result = <DateTime>[];
    DateTime current = startDate;
    while (!current.isAfter(endDate)) {
      result.add(current);
      current = current.add(Duration(days: intervalDays));
    }
    return result;
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'title': title,
    'note': note,
    'startDate': dateStorageKey(startDate),
    'endDate': dateStorageKey(endDate),
    'intervalDays': intervalDays,
    'taskTitle': taskTitle,
    'taskNote': taskNote,
    'taskStartMinute': taskStartMinute,
    'taskDurationMinutes': taskDurationMinutes,
    'taskPriority': taskPriority.name,
    'taskGroupId': taskGroupId,
    'createdAt': createdAt.toUtc().toIso8601String(),
    'updatedAt': updatedAt.toUtc().toIso8601String(),
  };

  GoalProgress progress(Iterable<PlannerTask> allTasks, DateTime now) {
    final DateTime today = dateOnly(now);
    final Map<DateTime, PlannerTask> byOccurrence = <DateTime, PlannerTask>{
      for (final PlannerTask task in allTasks)
        if (task.goalId == id && task.goalOccurrenceDate != null)
          dateOnly(task.goalOccurrenceDate!): task,
    };
    int completed = 0;
    int onTime = 0;
    int late = 0;
    int missed = 0;
    int due = 0;
    for (final DateTime occurrence in occurrenceDates) {
      final PlannerTask? task = byOccurrence[occurrence];
      final DateTime deadline = task?.date ?? occurrence;
      if (!deadline.isAfter(today)) {
        due += 1;
      }
      if (task?.isCompleted ?? false) {
        completed += 1;
        final DateTime completedDate = dateOnly(task!.completedAt!.toLocal());
        if (!completedDate.isAfter(deadline)) {
          onTime += 1;
        } else {
          late += 1;
        }
      } else if (deadline.isBefore(today)) {
        missed += 1;
      }
    }
    final int total = occurrenceDates.length;
    final double completion = total == 0 ? 0 : completed / total;
    final double punctuality = due == 0 ? 1 : (onTime + late * 0.6) / due;
    final double mood = due == 0
        ? 0.5
        : (punctuality * 0.7 + completion * 0.3).clamp(0, 1);
    return GoalProgress(
      total: total,
      completed: completed,
      onTime: onTime,
      late: late,
      missed: missed,
      completion: completion,
      mood: mood,
    );
  }
}

final class GoalProgress {
  const GoalProgress({
    required this.total,
    required this.completed,
    required this.onTime,
    required this.late,
    required this.missed,
    required this.completion,
    required this.mood,
  });

  final int total;
  final int completed;
  final int onTime;
  final int late;
  final int missed;
  final double completion;
  final double mood;

  String get emoji => switch (mood) {
    < 0.2 => '😭',
    < 0.4 => '😢',
    < 0.55 => '😕',
    < 0.7 => '🙂',
    < 0.85 => '😊',
    < 0.96 => '😄',
    _ => '🤩',
  };
}

int? _normalizeGoalDuration(int? startMinute, int? durationMinutes) {
  if (startMinute == null) {
    if (durationMinutes != null) {
      throw ArgumentError('Длительность требует времени начала');
    }
    return null;
  }
  if (startMinute < 0 || startMinute > 1439) {
    throw ArgumentError('Некорректное время задачи');
  }
  final int normalized = durationMinutes ?? 60;
  if (normalized < 15 ||
      normalized > 1440 ||
      normalized % 15 != 0 ||
      startMinute + normalized > 1440) {
    throw ArgumentError('Некорректная длительность задачи цели');
  }
  return normalized;
}
