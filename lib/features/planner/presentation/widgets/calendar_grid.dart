import 'package:flutter/material.dart';

import '../../../../core/date/calendar_date.dart';
import '../../../../core/date/date_formatters.dart';
import '../../domain/calendar_month.dart';
import '../../domain/planner_task.dart';

class CalendarGrid extends StatelessWidget {
  const CalendarGrid({
    required this.month,
    required this.selectedDate,
    required this.today,
    required this.tasksForDate,
    required this.taskColor,
    required this.onDateSelected,
    this.fillAvailableHeight = false,
    super.key,
  });

  final CalendarMonth month;
  final DateTime selectedDate;
  final DateTime today;
  final List<PlannerTask> Function(DateTime date) tasksForDate;
  final Color Function(PlannerTask task) taskColor;
  final ValueChanged<DateTime> onDateSelected;
  final bool fillAvailableHeight;

  @override
  Widget build(BuildContext context) {
    final List<DateTime> days = month.visibleDays;
    final Widget grid = LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final bool compact = constraints.maxWidth < 680;
        final SliverGridDelegate delegate = fillAvailableHeight
            ? SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 7,
                mainAxisExtent: constraints.maxHeight / 6,
              )
            : SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 7,
                childAspectRatio: compact ? 0.82 : 1.18,
              );

        return GridView.builder(
          padding: EdgeInsets.zero,
          shrinkWrap: !fillAvailableHeight,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: days.length,
          gridDelegate: delegate,
          itemBuilder: (BuildContext context, int index) {
            final DateTime day = days[index];
            return _CalendarDayCell(
              day: day,
              tasks: tasksForDate(day),
              isCurrentMonth: month.contains(day),
              isSelected: isSameDate(day, selectedDate),
              isToday: isSameDate(day, today),
              compact: compact,
              taskColor: taskColor,
              onTap: () => onDateSelected(day),
            );
          },
        );
      },
    );

    return Column(
      children: <Widget>[
        Container(
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: 4),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: Color(0xFFE8EAF1))),
          ),
          child: Row(
            children: weekdayShortNames
                .map(
                  (String value) => Expanded(
                    child: Center(
                      child: Text(
                        value,
                        style: Theme.of(context).textTheme.labelMedium
                            ?.copyWith(
                              color: const Color(0xFF52576A),
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                    ),
                  ),
                )
                .toList(growable: false),
          ),
        ),
        if (fillAvailableHeight) Expanded(child: grid) else grid,
      ],
    );
  }
}

class _CalendarDayCell extends StatelessWidget {
  const _CalendarDayCell({
    required this.day,
    required this.tasks,
    required this.isCurrentMonth,
    required this.isSelected,
    required this.isToday,
    required this.compact,
    required this.taskColor,
    required this.onTap,
  });

  final DateTime day;
  final List<PlannerTask> tasks;
  final bool isCurrentMonth;
  final bool isSelected;
  final bool isToday;
  final bool compact;
  final Color Function(PlannerTask task) taskColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Color numberColor = isCurrentMonth
        ? const Color(0xFF262A3B)
        : const Color(0xFFB1B6C5);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        hoverColor: const Color(0xFFF8F7FF),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          margin: isSelected ? const EdgeInsets.all(2) : EdgeInsets.zero,
          padding: EdgeInsets.fromLTRB(
            compact ? 5 : 10,
            compact ? 5 : 8,
            compact ? 5 : 10,
            compact ? 4 : 7,
          ),
          decoration: BoxDecoration(
            color: isSelected ? const Color(0xFFF5F2FF) : Colors.white,
            border: Border.all(
              color: isSelected
                  ? const Color(0xFF7A67F8)
                  : const Color(0xFFE9EBF1),
              width: isSelected ? 1.4 : 0.7,
            ),
            borderRadius: isSelected ? BorderRadius.circular(12) : null,
            boxShadow: isSelected
                ? const <BoxShadow>[
                    BoxShadow(
                      color: Color(0x1F5B47F7),
                      blurRadius: 16,
                      offset: Offset(0, 3),
                    ),
                  ]
                : null,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Align(
                alignment: isSelected
                    ? Alignment.centerLeft
                    : Alignment.topCenter,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  width: isToday || isSelected ? 28 : 24,
                  height: isToday || isSelected ? 28 : 24,
                  alignment: Alignment.center,
                  decoration: (isToday || isSelected)
                      ? BoxDecoration(
                          color: isToday
                              ? const Color(0xFF5B47F7)
                              : const Color(0xFF6752F4),
                          shape: BoxShape.circle,
                          boxShadow: isSelected
                              ? const <BoxShadow>[
                                  BoxShadow(
                                    color: Color(0x3D5B47F7),
                                    blurRadius: 9,
                                  ),
                                ]
                              : null,
                        )
                      : null,
                  child: Text(
                    '${day.day}',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: isToday || isSelected ? Colors.white : numberColor,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ),
              SizedBox(height: compact ? 3 : 6),
              if (compact && tasks.isNotEmpty)
                Wrap(
                  spacing: 3,
                  runSpacing: 3,
                  children: tasks
                      .take(4)
                      .map(
                        (PlannerTask task) => Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: taskColor(task),
                            shape: BoxShape.circle,
                          ),
                        ),
                      )
                      .toList(growable: false),
                ),
              if (!compact)
                _CalendarTaskPreviews(
                  tasks: tasks,
                  isSelected: isSelected,
                  taskColor: taskColor,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CalendarTaskPreviews extends StatelessWidget {
  const _CalendarTaskPreviews({
    required this.tasks,
    required this.isSelected,
    required this.taskColor,
  });

  final List<PlannerTask> tasks;
  final bool isSelected;
  final Color Function(PlannerTask task) taskColor;

  @override
  Widget build(BuildContext context) {
    if (tasks.isEmpty) return const SizedBox.shrink();

    // Selected previews have extra vertical padding. If there are more tasks
    // than can be shown, reserve one line for the compact "+N ещё" summary
    // instead of rendering it below three full rows and overflowing the cell.
    final int normalLimit = isSelected ? 3 : 2;
    final bool needsMoreLine = tasks.length > normalLimit;
    final int visibleCount = needsMoreLine && isSelected ? 2 : normalLimit;
    final int hiddenCount = tasks.length - visibleCount;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final PlannerTask task in tasks.take(visibleCount))
          _TaskPreview(
            task: task,
            accent: taskColor(task),
            emphasized: isSelected,
          ),
        if (hiddenCount > 0)
          Padding(
            padding: const EdgeInsets.only(left: 1, top: 1),
            child: Text(
              '+$hiddenCount ещё',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: const Color(0xFF6550F5),
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
      ],
    );
  }
}

class _TaskPreview extends StatelessWidget {
  const _TaskPreview({
    required this.task,
    required this.accent,
    required this.emphasized,
  });

  final PlannerTask task;
  final Color accent;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final String? time = task.startMinute == null
        ? null
        : formatMinutesOfDay(task.startMinute!);
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: emphasized
          ? const EdgeInsets.symmetric(horizontal: 4, vertical: 2)
          : EdgeInsets.zero,
      decoration: emphasized
          ? BoxDecoration(
              color: Colors.white.withValues(alpha: 0.66),
              borderRadius: BorderRadius.circular(6),
            )
          : null,
      child: Row(
        children: <Widget>[
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              time == null ? task.title : '$time · ${task.title}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: const Color(0xFF50566A),
                fontWeight: emphasized ? FontWeight.w600 : FontWeight.w500,
                decoration: task.isCompleted
                    ? TextDecoration.lineThrough
                    : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
