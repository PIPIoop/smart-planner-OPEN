import 'package:flutter/material.dart';

import '../../application/planner_view_model.dart';
import '../../domain/task_group.dart';

Future<void> showGroupManagerDialog({
  required BuildContext context,
  required PlannerViewModel viewModel,
}) async {
  await showDialog<void>(
    context: context,
    builder: (BuildContext dialogContext) => AlertDialog(
      title: const Text('Группы задач'),
      content: SizedBox(
        width: 520,
        child: ListenableBuilder(
          listenable: viewModel,
          builder: (BuildContext context, Widget? child) {
            if (viewModel.groups.isEmpty) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Text(
                  'Создайте группу и выберите для неё цвет. Задача может относиться только к одной группе.',
                  textAlign: TextAlign.center,
                ),
              );
            }
            return ListView.separated(
              shrinkWrap: true,
              itemCount: viewModel.groups.length,
              separatorBuilder: (_, _) => const Divider(height: 1),
              itemBuilder: (BuildContext context, int index) {
                final TaskGroup group = viewModel.groups[index];
                return ListTile(
                  leading: CircleAvatar(backgroundColor: group.color),
                  title: Text(group.name),
                  subtitle: Text(group.colorHex),
                  trailing: Wrap(
                    spacing: 4,
                    children: <Widget>[
                      IconButton(
                        tooltip: 'Редактировать группу',
                        onPressed: viewModel.isSaving
                            ? null
                            : () => _editGroup(dialogContext, viewModel, group),
                        icon: const Icon(Icons.edit_outlined),
                      ),
                      IconButton(
                        tooltip: 'Удалить группу',
                        onPressed: viewModel.isSaving
                            ? null
                            : () =>
                                  _deleteGroup(dialogContext, viewModel, group),
                        icon: const Icon(Icons.delete_outline),
                      ),
                    ],
                  ),
                );
              },
            );
          },
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.pop(dialogContext),
          child: const Text('Закрыть'),
        ),
        FilledButton.icon(
          onPressed: () => _editGroup(dialogContext, viewModel, null),
          icon: const Icon(Icons.add),
          label: const Text('Новая группа'),
        ),
      ],
    ),
  );
}

Future<void> _editGroup(
  BuildContext context,
  PlannerViewModel viewModel,
  TaskGroup? group,
) async {
  if (group == null &&
      viewModel.groups.length >= taskGroupColorPalette.length) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Все цвета палитры уже используются.')),
    );
    return;
  }
  final TaskGroupDraft? draft = await showDialog<TaskGroupDraft>(
    context: context,
    builder: (BuildContext context) => _GroupEditorDialog(
      group: group,
      unavailableColors: viewModel.groups
          .where((TaskGroup item) => item.id != group?.id)
          .map((TaskGroup item) => item.colorHex)
          .toSet(),
    ),
  );
  if (draft == null) return;
  try {
    if (group == null) {
      await viewModel.createGroup(draft);
    } else {
      await viewModel.updateGroup(group.id, draft);
    }
  } on Object {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось сохранить группу.')),
      );
    }
  }
}

Future<void> _deleteGroup(
  BuildContext context,
  PlannerViewModel viewModel,
  TaskGroup group,
) async {
  final bool? confirmed = await showDialog<bool>(
    context: context,
    builder: (BuildContext context) => AlertDialog(
      title: const Text('Удалить группу?'),
      content: Text(
        'Группа «${group.name}» будет удалена. Задачи останутся без группы.',
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('Удалить'),
        ),
      ],
    ),
  );
  if (confirmed != true) return;
  try {
    await viewModel.deleteGroup(group.id);
  } on Object {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось удалить группу.')),
      );
    }
  }
}

class _GroupEditorDialog extends StatefulWidget {
  const _GroupEditorDialog({
    required this.group,
    required this.unavailableColors,
  });
  final TaskGroup? group;
  final Set<String> unavailableColors;
  @override
  State<_GroupEditorDialog> createState() => _GroupEditorDialogState();
}

class _GroupEditorDialogState extends State<_GroupEditorDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameController;
  late String _colorHex;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.group?.name ?? '');
    _colorHex =
        widget.group?.colorHex ??
        taskGroupColorPalette.firstWhere(
          (String color) => !widget.unavailableColors.contains(color),
          orElse: () => taskGroupColorPalette.first,
        );
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    Navigator.pop(
      context,
      TaskGroupDraft(name: _nameController.text, colorHex: _colorHex),
    );
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.group == null ? 'Новая группа' : 'Редактировать группу'),
    content: SizedBox(
      width: 440,
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            TextFormField(
              controller: _nameController,
              autofocus: true,
              maxLength: 60,
              decoration: const InputDecoration(labelText: 'Название группы'),
              validator: (String? value) =>
                  value == null || value.trim().isEmpty
                  ? 'Введите название группы'
                  : null,
            ),
            const SizedBox(height: 12),
            const Text('Цвет', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: taskGroupColorPalette.map((String colorHex) {
                final bool selected = colorHex == _colorHex;
                final bool unavailable = widget.unavailableColors.contains(
                  colorHex,
                );
                return Semantics(
                  button: true,
                  label: 'Цвет группы $colorHex',
                  selected: selected,
                  enabled: !unavailable,
                  child: InkWell(
                    onTap: unavailable
                        ? null
                        : () => setState(() => _colorHex = colorHex),
                    borderRadius: BorderRadius.circular(99),
                    child: Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color: colorFromHex(
                          colorHex,
                        ).withValues(alpha: unavailable ? 0.25 : 1),
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: selected
                              ? const Color(0xFF111827)
                              : Colors.white,
                          width: selected ? 3 : 2,
                        ),
                        boxShadow: const <BoxShadow>[
                          BoxShadow(color: Color(0x22000000), blurRadius: 5),
                        ],
                      ),
                      child: selected
                          ? const Icon(
                              Icons.check,
                              color: Colors.white,
                              size: 20,
                            )
                          : null,
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    ),
    actions: <Widget>[
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Отмена'),
      ),
      FilledButton(
        onPressed: _submit,
        child: Text(widget.group == null ? 'Создать' : 'Сохранить'),
      ),
    ],
  );
}
