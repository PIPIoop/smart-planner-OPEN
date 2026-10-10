import 'package:flutter/material.dart';

import '../../../../core/date/date_formatters.dart';
import '../../domain/planner_task.dart';
import '../../domain/task_group.dart';

class TaskListPanel extends StatelessWidget {
  const TaskListPanel({
    required this.date,
    required this.tasks,
    required this.groups,
    required this.isSaving,
    required this.onAdd,
    required this.onToggle,
    required this.onEdit,
    required this.onDelete,
    this.fillAvailableHeight = false,
    super.key,
  });

  final DateTime date;
  final List<PlannerTask> tasks;
  final List<TaskGroup> groups;
  final bool isSaving;
  final VoidCallback onAdd;
  final ValueChanged<PlannerTask> onToggle;
  final ValueChanged<PlannerTask> onEdit;
  final ValueChanged<PlannerTask> onDelete;
  final bool fillAvailableHeight;

  @override
  Widget build(BuildContext context) {
    final int completed = tasks
        .where((PlannerTask task) => task.isCompleted)
        .length;
    final double progress = tasks.isEmpty ? 0 : completed / tasks.length;
    final Widget content = tasks.isEmpty
        ? const _EmptyDayIllustration()
        : fillAvailableHeight
        ? ListView.separated(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            itemCount: tasks.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (BuildContext context, int index) => _TaskRow(
              task: tasks[index],
              group: _findGroup(groups, tasks[index].groupId),
              enabled: !isSaving,
              onToggle: () => onToggle(tasks[index]),
              onEdit: () => onEdit(tasks[index]),
              onDelete: () => onDelete(tasks[index]),
            ),
          )
        : Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            child: Column(
              children: tasks
                  .map(
                    (PlannerTask task) => Column(
                      children: <Widget>[
                        _TaskRow(
                          task: task,
                          group: _findGroup(groups, task.groupId),
                          enabled: !isSaving,
                          onToggle: () => onToggle(task),
                          onEdit: () => onEdit(task),
                          onDelete: () => onDelete(task),
                        ),
                        const Divider(height: 1),
                      ],
                    ),
                  )
                  .toList(growable: false),
            ),
          );

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE9EBF2)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 17, 13, 10),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        _formatPanelDate(date),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(
                              color: const Color(0xFF202235),
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _taskCountLabel(tasks.length),
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: const Color(0xFF858B9E),
                        ),
                      ),
                    ],
                  ),
                ),
                _SoftIconButton(
                  tooltip: 'Добавить задачу на выбранную дату',
                  onPressed: isSaving ? null : onAdd,
                  icon: Icons.calendar_month_outlined,
                ),
              ],
            ),
          ),
          if (tasks.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 2, 14, 10),
              child: _FocusCard(
                progress: progress,
                completed: completed,
                total: tasks.length,
              ),
            ),
          if (isSaving) const LinearProgressIndicator(minHeight: 2),
          if (fillAvailableHeight) Expanded(child: content) else content,
        ],
      ),
    );
  }
}

class _FocusCard extends StatelessWidget {
  const _FocusCard({
    required this.progress,
    required this.completed,
    required this.total,
  });

  final double progress;
  final int completed;
  final int total;

  @override
  Widget build(BuildContext context) {
    final int percent = (progress * 100).round();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F6FF),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.auto_awesome, color: Color(0xFF6A53F5), size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text(
                  'Фокус дня',
                  style: TextStyle(
                    color: Color(0xFF5D4BE0),
                    fontWeight: FontWeight.w800,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  completed == total
                      ? 'План на день выполнен.'
                      : 'Закрыто $completed из $total задач.',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: const Color(0xFF656B7E),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 48,
            height: 48,
            child: Stack(
              alignment: Alignment.center,
              children: <Widget>[
                CircularProgressIndicator(
                  value: progress,
                  strokeWidth: 4,
                  backgroundColor: const Color(0xFFE6E2F8),
                  color: const Color(0xFF6550F5),
                ),
                Text(
                  '$percent%',
                  style: const TextStyle(
                    color: Color(0xFF5D4BE0),
                    fontWeight: FontWeight.w800,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TaskRow extends StatelessWidget {
  const _TaskRow({
    required this.task,
    required this.group,
    required this.enabled,
    required this.onToggle,
    required this.onEdit,
    required this.onDelete,
  });

  final PlannerTask task;
  final TaskGroup? group;
  final bool enabled;
  final VoidCallback onToggle;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final Color accent =
        group?.color ??
        switch (task.priority) {
          TaskPriority.low => const Color(0xFF34B86E),
          TaskPriority.normal => const Color(0xFF397CE9),
          TaskPriority.high => const Color(0xFFF04D4D),
        };

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Checkbox(
              value: task.isCompleted,
              onChanged: enabled ? (_) => onToggle() : null,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
          const SizedBox(width: 5),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  task.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: const Color(0xFF2F3346),
                    fontWeight: FontWeight.w700,
                    decoration: task.isCompleted
                        ? TextDecoration.lineThrough
                        : null,
                  ),
                ),
                if (task.note.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 3),
                  Text(
                    task.note,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: const Color(0xFF8A90A2),
                    ),
                  ),
                ],
                if (group != null) ...<Widget>[
                  const SizedBox(height: 4),
                  Text(
                    group!.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: accent,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          if (task.startMinute != null)
            Text(
              formatTaskTime(task),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: const Color(0xFF8B91A3),
                fontWeight: FontWeight.w600,
              ),
            )
          else if (task.deadlineDate != null)
            const Tooltip(
              message: 'Задача с дедлайном',
              child: Icon(
                Icons.flag_outlined,
                size: 15,
                color: Color(0xFFF09A28),
              ),
            ),
          const SizedBox(width: 7),
          Container(
            width: 7,
            height: 7,
            margin: const EdgeInsets.only(top: 5),
            decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
          ),
          PopupMenuButton<_TaskAction>(
            tooltip: 'Действия с задачей',
            enabled: enabled,
            padding: EdgeInsets.zero,
            iconSize: 18,
            icon: const Icon(Icons.more_vert),
            onSelected: (_TaskAction action) {
              switch (action) {
                case _TaskAction.edit:
                  onEdit();
                case _TaskAction.delete:
                  onDelete();
              }
            },
            itemBuilder: (_) => const <PopupMenuEntry<_TaskAction>>[
              PopupMenuItem<_TaskAction>(
                value: _TaskAction.edit,
                child: ListTile(
                  leading: Icon(Icons.edit_outlined),
                  title: Text('Редактировать'),
                  contentPadding: EdgeInsets.zero,
                ),
              ),
              PopupMenuItem<_TaskAction>(
                value: _TaskAction.delete,
                child: ListTile(
                  leading: Icon(Icons.delete_outline),
                  title: Text('Удалить'),
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

enum _TaskAction { edit, delete }

class _EmptyDayIllustration extends StatelessWidget {
  const _EmptyDayIllustration();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 22),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Container(
            width: 62,
            height: 62,
            decoration: const BoxDecoration(
              color: Color(0xFFF2F0FF),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.task_alt_outlined,
              size: 31,
              color: Color(0xFF6C58F5),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'На этот день задач нет',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
              color: const Color(0xFF343849),
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            'Добавь задачу или выбери другой день.',
            textAlign: TextAlign.center,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: const Color(0xFF858B9E)),
          ),
        ],
      ),
    );
  }
}

class _SoftIconButton extends StatelessWidget {
  const _SoftIconButton({
    required this.tooltip,
    required this.onPressed,
    required this.icon,
  });

  final String tooltip;
  final VoidCallback? onPressed;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: tooltip,
      onPressed: onPressed,
      icon: Icon(icon, size: 20),
      color: const Color(0xFF5B47F7),
      style: IconButton.styleFrom(
        backgroundColor: const Color(0xFFF4F1FF),
        side: const BorderSide(color: Color(0xFFE2DDFF)),
        minimumSize: const Size(42, 42),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}

String _taskCountLabel(int count) {
  final int mod10 = count % 10;
  final int mod100 = count % 100;
  if (mod10 == 1 && mod100 != 11) return '$count задача';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return '$count задачи';
  }
  return '$count задач';
}

String _formatPanelDate(DateTime date) {
  const List<String> weekdays = <String>[
    'Понедельник',
    'Вторник',
    'Среда',
    'Четверг',
    'Пятница',
    'Суббота',
    'Воскресенье',
  ];
  return '${weekdays[date.weekday - 1]}, ${formatFullDate(date)}';
}

TaskGroup? _findGroup(List<TaskGroup> groups, String? groupId) {
  if (groupId == null) return null;
  for (final TaskGroup group in groups) {
    if (group.id == groupId) return group;
  }
  return null;
}
