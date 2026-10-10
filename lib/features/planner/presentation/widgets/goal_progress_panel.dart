import 'package:flutter/material.dart';

import '../../domain/planner_goal.dart';
import '../../domain/planner_task.dart';

class GoalProgressPanel extends StatelessWidget {
  const GoalProgressPanel({
    required this.goals,
    required this.tasks,
    required this.expanded,
    required this.now,
    required this.onToggleExpanded,
    required this.onAdd,
    required this.onDelete,
    super.key,
  });

  final List<PlannerGoal> goals;
  final List<PlannerTask> tasks;
  final bool expanded;
  final DateTime now;
  final VoidCallback onToggleExpanded;
  final VoidCallback onAdd;
  final ValueChanged<PlannerGoal> onDelete;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE9EBF2)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 14, 10, 12),
            child: Row(
              children: <Widget>[
                const Icon(
                  Icons.track_changes_outlined,
                  color: Color(0xFF5B47F7),
                  size: 21,
                ),
                const SizedBox(width: 9),
                const Expanded(
                  child: Text(
                    'Цели',
                    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
                  ),
                ),
                IconButton(
                  tooltip: 'Новая цель',
                  onPressed: onAdd,
                  icon: const Icon(Icons.add_circle_outline, size: 21),
                  color: const Color(0xFF3A4053),
                  visualDensity: VisualDensity.compact,
                ),
                IconButton(
                  tooltip: expanded ? 'Скрыть цели' : 'Показать цели',
                  onPressed: onToggleExpanded,
                  icon: Icon(
                    expanded ? Icons.expand_less : Icons.expand_more,
                    size: 20,
                  ),
                  color: const Color(0xFF7B8194),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
          ),
          if (expanded) ...<Widget>[
            if (goals.isEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 4, 18, 18),
                child: Text(
                  'Создай цель — Smart Planner автоматически разложит повторяющиеся задачи по календарю.',
                  textAlign: TextAlign.left,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF81879A),
                    height: 1.4,
                  ),
                ),
              )
            else
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 225),
                child: ListView.separated(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(18, 1, 14, 17),
                  itemCount: goals.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 13),
                  itemBuilder: (BuildContext context, int index) {
                    final PlannerGoal goal = goals[index];
                    return _GoalRow(
                      goal: goal,
                      progress: goal.progress(tasks, now),
                      onDelete: () => onDelete(goal),
                    );
                  },
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _GoalRow extends StatelessWidget {
  const _GoalRow({
    required this.goal,
    required this.progress,
    required this.onDelete,
  });

  final PlannerGoal goal;
  final GoalProgress progress;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final int percent = (progress.completion * 100).round();
    final Color color = _progressColor(percent);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                goal.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: const Color(0xFF343849),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '${progress.completed} / ${progress.total}',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: const Color(0xFF6E7488),
                fontWeight: FontWeight.w600,
              ),
            ),
            PopupMenuButton<String>(
              tooltip: 'Действия с целью',
              padding: EdgeInsets.zero,
              iconSize: 18,
              icon: const Icon(Icons.more_horiz),
              onSelected: (_) => onDelete(),
              itemBuilder: (_) => const <PopupMenuEntry<String>>[
                PopupMenuItem<String>(
                  value: 'delete',
                  child: ListTile(
                    leading: Icon(Icons.delete_outline),
                    title: Text('Удалить цель'),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        Semantics(
          label: 'Прогресс цели $percent процентов',
          child: LinearProgressIndicator(
            value: progress.completion,
            minHeight: 6,
            borderRadius: BorderRadius.circular(999),
            backgroundColor: const Color(0xFFEEF0F4),
            color: color,
          ),
        ),
        const SizedBox(height: 5),
        Row(
          children: <Widget>[
            Text(
              '$percent%',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: color,
                fontWeight: FontWeight.w800,
              ),
            ),
            const Spacer(),
            Text(
              'Вовремя ${progress.onTime} · Позже ${progress.late} · Пропущено ${progress.missed}',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: const Color(0xFF9A9FAF),
                fontSize: 10,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

Color _progressColor(int percent) {
  if (percent >= 75) return const Color(0xFF5B47F7);
  if (percent >= 45) return const Color(0xFF31B76E);
  return const Color(0xFF2D89E5);
}
