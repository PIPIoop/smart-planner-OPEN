import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../../core/date/date_formatters.dart';
import '../../domain/planner_task.dart';
import '../../domain/task_group.dart';

Future<TaskDraft?> showTaskEditorDialog({
  required BuildContext context,
  required DateTime initialDate,
  PlannerTask? task,
  List<TaskGroup> groups = const <TaskGroup>[],
}) {
  return showDialog<TaskDraft>(
    context: context,
    barrierDismissible: false,
    barrierColor: const Color(0x663B3A64),
    builder: (BuildContext dialogContext) {
      return _TaskEditorDialog(
        initialDate: initialDate,
        task: task,
        groups: groups,
      );
    },
  );
}

class _TaskEditorDialog extends StatefulWidget {
  const _TaskEditorDialog({
    required this.initialDate,
    required this.task,
    required this.groups,
  });

  final DateTime initialDate;
  final PlannerTask? task;
  final List<TaskGroup> groups;

  @override
  State<_TaskEditorDialog> createState() => _TaskEditorDialogState();
}

class _TaskEditorDialogState extends State<_TaskEditorDialog> {
  static const List<int> _durationOptions = <int>[
    15,
    30,
    45,
    60,
    90,
    120,
    180,
    240,
  ];

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _titleController;
  late final TextEditingController _noteController;
  late DateTime _date;
  int? _startMinute;
  int? _durationMinutes;
  DateTime? _deadlineDate;
  int? _deadlineMinute;
  late bool _deadlineEnabled;
  late TaskPriority _priority;
  String? _groupId;

  bool get _isEditing => widget.task != null;

  List<int> get _availableDurationOptions {
    final int? startMinute = _startMinute;
    if (startMinute == null) return const <int>[];
    return _durationOptions
        .where((int duration) => startMinute + duration <= 24 * 60)
        .toList(growable: false);
  }

  String? get _endTimeText {
    if (_startMinute == null || _durationMinutes == null) return null;
    return formatMinutesOfDay(_startMinute! + _durationMinutes!);
  }

  @override
  void initState() {
    super.initState();
    final PlannerTask? task = widget.task;
    _titleController = TextEditingController(text: task?.title ?? '');
    _noteController = TextEditingController(text: task?.note ?? '');
    _date = task?.date ?? widget.initialDate;
    _startMinute = task?.startMinute;
    _durationMinutes = task?.durationMinutes;
    _deadlineDate = task?.deadlineDate;
    _deadlineMinute = task?.deadlineMinute;
    _deadlineEnabled = task?.deadlineDate != null;
    _priority = task?.priority ?? TaskPriority.normal;
    _groupId = task?.groupId;
  }

  @override
  void dispose() {
    _titleController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final DateTime? selected = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100, 12, 31),
    );
    if (selected != null) setState(() => _date = selected);
  }

  Future<void> _pickTime() async {
    final int currentMinute = _startMinute ?? 9 * 60;
    final TimeOfDay? selected = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(
        hour: currentMinute ~/ 60,
        minute: currentMinute % 60,
      ),
    );
    if (selected == null) return;
    final int startMinute = selected.hour * 60 + selected.minute;
    final List<int> available = _durationOptions
        .where((int duration) => startMinute + duration <= 24 * 60)
        .toList(growable: false);
    if (available.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Выберите время не позднее 23:45: минимальная длительность — 15 минут.',
            ),
          ),
        );
      }
      return;
    }
    final int currentDuration = _durationMinutes ?? 60;
    setState(() {
      _startMinute = startMinute;
      _durationMinutes = available.contains(currentDuration)
          ? currentDuration
          : available.contains(60)
          ? 60
          : available.last;
    });
  }

  Future<void> _pickDeadlineDate() async {
    final DateTime initial = _deadlineDate ?? _date;
    final DateTime? selected = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100, 12, 31),
    );
    if (selected != null) setState(() => _deadlineDate = selected);
  }

  Future<void> _pickDeadlineTime() async {
    final int current = _deadlineMinute ?? 18 * 60;
    final TimeOfDay? selected = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: current ~/ 60, minute: current % 60),
    );
    if (selected != null) {
      setState(() {
        _deadlineMinute = selected.hour * 60 + selected.minute;
        _deadlineDate ??= _date;
      });
    }
  }

  void _toggleDeadline(bool enabled) {
    setState(() {
      _deadlineEnabled = enabled;
      if (enabled) {
        _deadlineDate ??= _date;
      } else {
        _deadlineDate = null;
        _deadlineMinute = null;
      }
    });
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    Navigator.of(context).pop(
      TaskDraft(
        title: _titleController.text,
        note: _noteController.text,
        date: _date,
        startMinute: _startMinute,
        durationMinutes: _durationMinutes,
        deadlineDate: _deadlineEnabled ? _deadlineDate : null,
        deadlineMinute: _deadlineEnabled ? _deadlineMinute : null,
        priority: _priority,
        groupId: _groupId,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final Size viewport = MediaQuery.sizeOf(context);
    // Give the dialog an explicit finite size. This is important not only on
    // the web, but also in widget tests where the default viewport is 800x600:
    // a flex child inside a merely max-constrained Dialog can otherwise enter
    // a layout cycle and leave RenderPhysicalShape without a size.
    final double dialogWidth = math.min(720, viewport.width * 0.92);
    final double dialogHeight = math.min(860, viewport.height * 0.92);
    final bool shortViewport = dialogHeight < 620;

    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
      backgroundColor: const Color(0xFFFEFEFF),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        width: dialogWidth,
        height: dialogHeight,
        child: Column(
          children: <Widget>[
            Expanded(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(
                  shortViewport ? 24 : 32,
                  shortViewport ? 20 : 28,
                  shortViewport ? 24 : 32,
                  shortViewport ? 18 : 26,
                ),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      _DialogTitle(
                        title: _isEditing
                            ? 'Редактировать задачу'
                            : 'Новая задача',
                        onClose: () => Navigator.of(context).pop(),
                      ),
                      const SizedBox(height: 26),
                      const _FieldLabel(text: 'Название', isRequired: true),
                      const SizedBox(height: 8),
                      TextFormField(
                        controller: _titleController,
                        autofocus: true,
                        maxLength: 120,
                        decoration: const InputDecoration(
                          hintText: 'Например, подготовить отчёт',
                          counterText: '',
                        ),
                        validator: (String? value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Введите название задачи';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 18),
                      const _FieldLabel(text: 'Описание'),
                      const SizedBox(height: 8),
                      TextFormField(
                        controller: _noteController,
                        minLines: 3,
                        maxLines: 5,
                        maxLength: 1000,
                        decoration: const InputDecoration(
                          hintText: 'Добавьте детали задачи…',
                          alignLabelWithHint: true,
                        ),
                      ),
                      const SizedBox(height: 18),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: <Widget>[
                          _ActionChipButton(
                            icon: Icons.calendar_today_outlined,
                            label: formatShortDate(_date),
                            onPressed: _pickDate,
                            highlighted: true,
                          ),
                          _ActionChipButton(
                            icon: Icons.schedule_outlined,
                            label: _startMinute == null
                                ? 'Добавить время'
                                : formatMinutesOfDay(_startMinute!),
                            onPressed: _pickTime,
                          ),
                          if (_startMinute != null)
                            _ActionChipButton(
                              icon: Icons.close,
                              label: 'Без времени',
                              onPressed: () => setState(() {
                                _startMinute = null;
                                _durationMinutes = null;
                              }),
                            ),
                        ],
                      ),
                      if (_startMinute != null) ...<Widget>[
                        const SizedBox(height: 18),
                        DropdownButtonFormField<int>(
                          initialValue: _durationMinutes,
                          decoration: InputDecoration(
                            labelText: 'Длительность',
                            helperText: _endTimeText == null
                                ? null
                                : 'Окончание: $_endTimeText',
                            prefixIcon: const Icon(Icons.timelapse_outlined),
                          ),
                          items: _availableDurationOptions
                              .map(
                                (int value) => DropdownMenuItem<int>(
                                  value: value,
                                  child: Text(_durationLabel(value)),
                                ),
                              )
                              .toList(growable: false),
                          onChanged: (int? value) =>
                              setState(() => _durationMinutes = value),
                        ),
                      ],
                      const SizedBox(height: 18),
                      LayoutBuilder(
                        builder:
                            (BuildContext context, BoxConstraints constraints) {
                              final bool stacked = constraints.maxWidth < 520;
                              final Widget group =
                                  DropdownButtonFormField<String?>(
                                    initialValue: _groupId,
                                    decoration: const InputDecoration(
                                      labelText: 'Группа',
                                      prefixIcon: Icon(Icons.folder_outlined),
                                    ),
                                    items: <DropdownMenuItem<String?>>[
                                      const DropdownMenuItem<String?>(
                                        value: null,
                                        child: Text('Без группы'),
                                      ),
                                      ...widget.groups.map(
                                        (TaskGroup group) =>
                                            DropdownMenuItem<String?>(
                                              value: group.id,
                                              child: Row(
                                                mainAxisSize: MainAxisSize.min,
                                                children: <Widget>[
                                                  Container(
                                                    width: 10,
                                                    height: 10,
                                                    decoration: BoxDecoration(
                                                      color: group.color,
                                                      shape: BoxShape.circle,
                                                    ),
                                                  ),
                                                  const SizedBox(width: 8),
                                                  ConstrainedBox(
                                                    constraints:
                                                        const BoxConstraints(
                                                          maxWidth: 190,
                                                        ),
                                                    child: Text(
                                                      group.name,
                                                      maxLines: 1,
                                                      overflow:
                                                          TextOverflow.ellipsis,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                      ),
                                    ],
                                    onChanged: (String? value) =>
                                        setState(() => _groupId = value),
                                  );
                              final Widget priority =
                                  DropdownButtonFormField<TaskPriority>(
                                    initialValue: _priority,
                                    decoration: const InputDecoration(
                                      labelText: 'Приоритет',
                                      prefixIcon: Icon(Icons.flag_outlined),
                                    ),
                                    items: TaskPriority.values
                                        .map(
                                          (TaskPriority value) =>
                                              DropdownMenuItem<TaskPriority>(
                                                value: value,
                                                child: Text(value.label),
                                              ),
                                        )
                                        .toList(growable: false),
                                    onChanged: (TaskPriority? value) {
                                      if (value != null) {
                                        setState(() => _priority = value);
                                      }
                                    },
                                  );
                              if (stacked) {
                                return Column(
                                  children: <Widget>[
                                    group,
                                    const SizedBox(height: 12),
                                    priority,
                                  ],
                                );
                              }
                              return Row(
                                children: <Widget>[
                                  Expanded(child: group),
                                  const SizedBox(width: 12),
                                  Expanded(child: priority),
                                ],
                              );
                            },
                      ),
                      const SizedBox(height: 18),
                      _DeadlineCard(
                        enabled: _deadlineEnabled,
                        date: _deadlineDate,
                        minute: _deadlineMinute,
                        onToggle: _toggleDeadline,
                        onPickDate: _pickDeadlineDate,
                        onPickTime: _pickDeadlineTime,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            Container(
              padding: EdgeInsets.fromLTRB(
                shortViewport ? 24 : 32,
                shortViewport ? 12 : 18,
                shortViewport ? 24 : 32,
                shortViewport ? 14 : 22,
              ),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: Color(0xFFECEBF4))),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Отмена'),
                  ),
                  const SizedBox(width: 12),
                  FilledButton(
                    onPressed: _submit,
                    style: FilledButton.styleFrom(
                      minimumSize: Size(132, shortViewport ? 44 : 50),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    child: Text(_isEditing ? 'Сохранить' : 'Создать'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DialogTitle extends StatelessWidget {
  const _DialogTitle({required this.title, required this.onClose});
  final String title;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: Text(
            title,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              color: const Color(0xFF17162A),
              fontWeight: FontWeight.w900,
              letterSpacing: -0.5,
            ),
          ),
        ),
        IconButton(
          tooltip: 'Закрыть',
          onPressed: onClose,
          icon: const Icon(Icons.close),
          style: IconButton.styleFrom(
            side: const BorderSide(color: Color(0xFFE2E1EC)),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ],
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.text, this.isRequired = false});
  final String text;
  final bool isRequired;

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        text: text,
        children: <InlineSpan>[
          if (isRequired)
            const TextSpan(
              text: ' •',
              style: TextStyle(color: Color(0xFF654BF7)),
            ),
        ],
      ),
      style: Theme.of(context).textTheme.labelLarge?.copyWith(
        color: const Color(0xFF313247),
        fontWeight: FontWeight.w700,
      ),
    );
  }
}

class _ActionChipButton extends StatelessWidget {
  const _ActionChipButton({
    required this.icon,
    required this.label,
    required this.onPressed,
    this.highlighted = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 19),
      label: Text(label),
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF5A47F7),
        backgroundColor: highlighted ? const Color(0xFFF6F3FF) : Colors.white,
        side: BorderSide(
          color: highlighted
              ? const Color(0xFFE2DDFF)
              : const Color(0xFFE5E4ED),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    );
  }
}

class _DeadlineCard extends StatelessWidget {
  const _DeadlineCard({
    required this.enabled,
    required this.date,
    required this.minute,
    required this.onToggle,
    required this.onPickDate,
    required this.onPickTime,
  });

  final bool enabled;
  final DateTime? date;
  final int? minute;
  final ValueChanged<bool> onToggle;
  final VoidCallback onPickDate;
  final VoidCallback onPickTime;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: enabled ? const Color(0xFFFBFAFF) : Colors.white,
        border: Border.all(
          color: enabled ? const Color(0xFFDED8FF) : const Color(0xFFE8E7EF),
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 42,
                height: 42,
                decoration: const BoxDecoration(
                  color: Color(0xFFF1EEFF),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.notifications_none_outlined,
                  color: Color(0xFF5A47F7),
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Дедлайн',
                      style: TextStyle(fontWeight: FontWeight.w800),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Укажите срок, если задача должна быть завершена к определённому моменту',
                      style: TextStyle(color: Color(0xFF81869A), fontSize: 12),
                    ),
                  ],
                ),
              ),
              Switch(value: enabled, onChanged: onToggle),
            ],
          ),
          if (enabled) ...<Widget>[
            const SizedBox(height: 12),
            Row(
              children: <Widget>[
                Expanded(
                  child: _ActionChipButton(
                    icon: Icons.event_available_outlined,
                    label: date == null
                        ? 'Дата дедлайна'
                        : formatShortDate(date!),
                    onPressed: onPickDate,
                    highlighted: true,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _ActionChipButton(
                    icon: Icons.schedule_outlined,
                    label: minute == null
                        ? 'Без точного времени'
                        : formatMinutesOfDay(minute!),
                    onPressed: onPickTime,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

String _durationLabel(int value) {
  if (value < 60) return '$value мин';
  if (value % 60 == 0) return '${value ~/ 60} ч';
  return '${value ~/ 60} ч ${value % 60} мин';
}
