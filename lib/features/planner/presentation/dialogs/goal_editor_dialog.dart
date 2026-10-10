import 'package:flutter/material.dart';

import '../../domain/planner_goal.dart';
import '../../domain/planner_task.dart';

Future<GoalDraft?> showGoalEditorDialog({
  required BuildContext context,
  required DateTime initialDate,
}) {
  return showDialog<GoalDraft>(
    context: context,
    barrierColor: const Color(0x663B3A64),
    builder: (_) => _GoalEditorDialog(initialDate: initialDate),
  );
}

class _GoalEditorDialog extends StatefulWidget {
  const _GoalEditorDialog({required this.initialDate});
  final DateTime initialDate;

  @override
  State<_GoalEditorDialog> createState() => _GoalEditorDialogState();
}

class _GoalEditorDialogState extends State<_GoalEditorDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _title;
  late final TextEditingController _taskTitle;
  final TextEditingController _note = TextEditingController();
  final TextEditingController _interval = TextEditingController(text: '2');
  late DateTime _startDate;
  late DateTime _endDate;
  TimeOfDay? _time;
  TaskPriority _priority = TaskPriority.normal;
  String _lastAutoTaskTitle = '';

  @override
  void initState() {
    super.initState();
    _startDate = widget.initialDate;
    _endDate = widget.initialDate.add(const Duration(days: 30));
    _title = TextEditingController();
    _taskTitle = TextEditingController();
    _title.addListener(_copyInitialTitle);
  }

  void _copyInitialTitle() {
    if (_taskTitle.text == _lastAutoTaskTitle) {
      _taskTitle.text = _title.text;
      _lastAutoTaskTitle = _title.text;
      _taskTitle.selection = TextSelection.collapsed(
        offset: _taskTitle.text.length,
      );
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _taskTitle.dispose();
    _note.dispose();
    _interval.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720, maxHeight: 900),
        child: Material(
          color: const Color(0xFFFEFEFF),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(32, 28, 32, 26),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                'Новая цель',
                                style: Theme.of(context).textTheme.headlineSmall
                                    ?.copyWith(
                                      color: const Color(0xFF17162A),
                                      fontWeight: FontWeight.w900,
                                      letterSpacing: -0.5,
                                    ),
                              ),
                            ),
                            IconButton(
                              tooltip: 'Закрыть',
                              onPressed: () => Navigator.pop(context),
                              icon: const Icon(Icons.close),
                              style: IconButton.styleFrom(
                                side: const BorderSide(
                                  color: Color(0xFFE2E1EC),
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 24),
                        TextFormField(
                          controller: _title,
                          autofocus: true,
                          decoration: const InputDecoration(
                            hintText: 'Название цели',
                            prefixIcon: Icon(Icons.track_changes_outlined),
                          ),
                          validator: _requiredText,
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _taskTitle,
                          decoration: const InputDecoration(
                            hintText: 'Название повторяющейся задачи',
                            prefixIcon: Icon(Icons.sync_outlined),
                          ),
                          validator: _requiredText,
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _note,
                          minLines: 3,
                          maxLines: 5,
                          maxLength: 1000,
                          decoration: const InputDecoration(
                            hintText: 'Описание (необязательно)',
                            alignLabelWithHint: true,
                            prefixIcon: Padding(
                              padding: EdgeInsets.only(bottom: 58),
                              child: Icon(Icons.format_list_bulleted_outlined),
                            ),
                          ),
                        ),
                        const SizedBox(height: 14),
                        LayoutBuilder(
                          builder:
                              (
                                BuildContext context,
                                BoxConstraints constraints,
                              ) {
                                final bool stacked = constraints.maxWidth < 520;
                                final Widget start = _GoalDateButton(
                                  label: 'Начало',
                                  date: _startDate,
                                  onPressed: () => _pickDate(true),
                                );
                                final Widget end = _GoalDateButton(
                                  label: 'Окончание',
                                  date: _endDate,
                                  onPressed: () => _pickDate(false),
                                );
                                if (stacked) {
                                  return Column(
                                    children: <Widget>[
                                      start,
                                      const SizedBox(height: 12),
                                      end,
                                    ],
                                  );
                                }
                                return Row(
                                  children: <Widget>[
                                    Expanded(child: start),
                                    const SizedBox(width: 12),
                                    Expanded(child: end),
                                  ],
                                );
                              },
                        ),
                        const SizedBox(height: 14),
                        LayoutBuilder(
                          builder:
                              (
                                BuildContext context,
                                BoxConstraints constraints,
                              ) {
                                final bool stacked = constraints.maxWidth < 520;
                                final Widget interval = _IntervalField(
                                  controller: _interval,
                                  onChanged: () => setState(() {}),
                                );
                                final Widget time = OutlinedButton.icon(
                                  onPressed: _pickTime,
                                  icon: const Icon(Icons.schedule_outlined),
                                  label: Align(
                                    alignment: Alignment.centerLeft,
                                    child: Text(
                                      _time == null
                                          ? 'Без времени'
                                          : _time!.format(context),
                                    ),
                                  ),
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: const Color(0xFF5A47F7),
                                    side: const BorderSide(
                                      color: Color(0xFFDED9F8),
                                    ),
                                    minimumSize: const Size.fromHeight(58),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(14),
                                    ),
                                  ),
                                );
                                if (stacked) {
                                  return Column(
                                    children: <Widget>[
                                      interval,
                                      const SizedBox(height: 12),
                                      time,
                                    ],
                                  );
                                }
                                return Row(
                                  children: <Widget>[
                                    Expanded(child: interval),
                                    const SizedBox(width: 12),
                                    Expanded(child: time),
                                  ],
                                );
                              },
                        ),
                        const SizedBox(height: 14),
                        DropdownButtonFormField<TaskPriority>(
                          initialValue: _priority,
                          decoration: const InputDecoration(
                            labelText: 'Приоритет задач',
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
                          onChanged: (TaskPriority? value) =>
                              setState(() => _priority = value ?? _priority),
                        ),
                        const SizedBox(height: 14),
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFBFAFF),
                            border: Border.all(color: const Color(0xFFE6E2FA)),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Row(
                            children: <Widget>[
                              CircleAvatar(
                                radius: 20,
                                backgroundColor: Color(0xFFF0ECFF),
                                child: Icon(
                                  Icons.auto_awesome_outlined,
                                  color: Color(0xFF5A47F7),
                                  size: 20,
                                ),
                              ),
                              SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: <Widget>[
                                    Text(
                                      'Автоматическое расписание',
                                      style: TextStyle(
                                        fontWeight: FontWeight.w800,
                                      ),
                                    ),
                                    SizedBox(height: 2),
                                    Text(
                                      'После создания цель добавит повторяющиеся задачи в выбранный период.',
                                      style: TextStyle(
                                        color: Color(0xFF81869A),
                                        fontSize: 12,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (_endDate.isBefore(_startDate))
                          const Padding(
                            padding: EdgeInsets.only(top: 12),
                            child: Text(
                              'Дата окончания должна быть не раньше начала',
                              style: TextStyle(color: Colors.red),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.fromLTRB(32, 18, 32, 22),
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: Color(0xFFECEBF4))),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: <Widget>[
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Отмена'),
                    ),
                    const SizedBox(width: 12),
                    FilledButton.icon(
                      onPressed: _submit,
                      icon: const Icon(Icons.auto_awesome_outlined, size: 18),
                      label: const Text('Создать цель'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(170, 50),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String? _requiredText(String? value) =>
      (value ?? '').trim().isEmpty ? 'Заполните поле' : null;

  Future<void> _pickDate(bool start) async {
    final DateTime current = start ? _startDate : _endDate;
    final DateTime? value = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
    );
    if (value != null) {
      setState(() => start ? _startDate = value : _endDate = value);
    }
  }

  Future<void> _pickTime() async {
    final TimeOfDay? value = await showTimePicker(
      context: context,
      initialTime: _time ?? const TimeOfDay(hour: 18, minute: 0),
    );
    if (value != null) setState(() => _time = value);
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false) ||
        _endDate.isBefore(_startDate)) {
      setState(() {});
      return;
    }
    final TimeOfDay? time = _time;
    Navigator.pop(
      context,
      GoalDraft(
        title: _title.text,
        taskTitle: _taskTitle.text,
        note: _note.text,
        startDate: _startDate,
        endDate: _endDate,
        intervalDays: int.parse(_interval.text),
        taskStartMinute: time == null ? null : time.hour * 60 + time.minute,
        taskPriority: _priority,
      ),
    );
  }
}

class _GoalDateButton extends StatelessWidget {
  const _GoalDateButton({
    required this.label,
    required this.date,
    required this.onPressed,
  });

  final String label;
  final DateTime date;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: const Icon(Icons.calendar_today_outlined),
      label: Align(
        alignment: Alignment.centerLeft,
        child: Text('$label: ${_formatDate(date)}'),
      ),
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF5A47F7),
        side: const BorderSide(color: Color(0xFFDED9F8)),
        minimumSize: const Size.fromHeight(58),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    );
  }
}

class _IntervalField extends StatelessWidget {
  const _IntervalField({required this.controller, required this.onChanged});

  final TextEditingController controller;
  final VoidCallback onChanged;

  void _adjust(int delta) {
    final int current = int.tryParse(controller.text) ?? 1;
    final int next = (current + delta).clamp(1, 365).toInt();
    controller.text = '$next';
    controller.selection = TextSelection.collapsed(
      offset: controller.text.length,
    );
    onChanged();
  }

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      textAlign: TextAlign.center,
      keyboardType: TextInputType.number,
      decoration: InputDecoration(
        labelText: 'Выполнять каждые N дней',
        prefixIcon: IconButton(
          tooltip: 'Уменьшить интервал',
          onPressed: () => _adjust(-1),
          icon: const Icon(Icons.remove),
        ),
        suffixIcon: IconButton(
          tooltip: 'Увеличить интервал',
          onPressed: () => _adjust(1),
          icon: const Icon(Icons.add),
        ),
      ),
      validator: (String? value) {
        final int? number = int.tryParse(value ?? '');
        return number == null || number < 1 || number > 365
            ? 'Введите число 1–365'
            : null;
      },
    );
  }
}

String _formatDate(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}';
