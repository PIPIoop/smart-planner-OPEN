import 'package:flutter/material.dart';

import '../../../../core/date/calendar_date.dart';
import '../../domain/planner_goal.dart';
import '../../domain/planner_task.dart';

class HabitStreakPanel extends StatelessWidget {
  const HabitStreakPanel({
    required this.goals,
    required this.tasks,
    required this.referenceDate,
    required this.today,
    super.key,
  });

  final List<PlannerGoal> goals;
  final List<PlannerTask> tasks;
  final DateTime referenceDate;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final DateTime weekStart = dateOnly(
      referenceDate.subtract(Duration(days: referenceDate.weekday - 1)),
    );
    final List<DateTime> week = List<DateTime>.generate(
      7,
      (int index) => weekStart.add(Duration(days: index)),
    );
    final List<PlannerGoal> visible = goals.take(3).toList(growable: false);

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE9EBF2)),
      ),
      padding: const EdgeInsets.fromLTRB(18, 15, 18, 17),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.local_fire_department_outlined,
                color: Color(0xFFF18B2B),
                size: 20,
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Привычки',
                  style: TextStyle(fontWeight: FontWeight.w900, fontSize: 15),
                ),
              ),
              Text(
                '7 дней',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: const Color(0xFF858B9E),
                ),
              ),
            ],
          ),
          const SizedBox(height: 13),
          if (visible.isEmpty)
            Text(
              'Повторяющиеся цели появятся здесь как серия выполнения.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: const Color(0xFF858B9E),
                height: 1.4,
              ),
            )
          else
            for (int index = 0; index < visible.length; index++) ...<Widget>[
              if (index > 0) const SizedBox(height: 10),
              _HabitRow(
                goal: visible[index],
                tasks: tasks,
                days: week,
                today: today,
                color: _habitColor(index),
              ),
            ],
        ],
      ),
    );
  }
}

class _HabitRow extends StatelessWidget {
  const _HabitRow({
    required this.goal,
    required this.tasks,
    required this.days,
    required this.today,
    required this.color,
  });

  final PlannerGoal goal;
  final List<PlannerTask> tasks;
  final List<DateTime> days;
  final DateTime today;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        SizedBox(
          width: 92,
          child: Text(
            goal.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: const Color(0xFF343849),
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: days
                .map((DateTime day) {
                  final bool scheduled = _isScheduled(day);
                  final PlannerTask? task = _taskFor(day);
                  final bool completed = task?.isCompleted ?? false;
                  final bool missed =
                      scheduled &&
                      !completed &&
                      dateOnly(day).isBefore(dateOnly(today));
                  return Tooltip(
                    message: scheduled
                        ? completed
                              ? 'Выполнено'
                              : missed
                              ? 'Пропущено'
                              : 'Запланировано'
                        : 'Нет выполнения',
                    child: Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: completed
                            ? color
                            : missed
                            ? const Color(0xFFF4A12A)
                            : scheduled
                            ? Colors.white
                            : const Color(0xFFF0F1F5),
                        border: scheduled && !completed && !missed
                            ? Border.all(
                                color: const Color(0xFFD4D7E1),
                                width: 1.5,
                              )
                            : null,
                      ),
                    ),
                  );
                })
                .toList(growable: false),
          ),
        ),
      ],
    );
  }

  bool _isScheduled(DateTime day) {
    final DateTime normalized = dateOnly(day);
    if (normalized.isBefore(goal.startDate) ||
        normalized.isAfter(goal.endDate)) {
      return false;
    }
    return normalized.difference(goal.startDate).inDays % goal.intervalDays ==
        0;
  }

  PlannerTask? _taskFor(DateTime day) {
    for (final PlannerTask task in tasks) {
      if (task.goalId == goal.id &&
          task.goalOccurrenceDate != null &&
          isSameDate(task.goalOccurrenceDate!, day)) {
        return task;
      }
    }
    return null;
  }
}

Color _habitColor(int index) => switch (index % 3) {
  0 => const Color(0xFF6550F5),
  1 => const Color(0xFF2D8BE7),
  _ => const Color(0xFF35B96F),
};
