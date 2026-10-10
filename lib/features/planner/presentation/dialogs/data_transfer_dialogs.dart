import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../domain/task_filter.dart';

Future<void> showExportDialog({
  required BuildContext context,
  required String json,
}) {
  return showDialog<void>(
    context: context,
    builder: (BuildContext dialogContext) {
      return AlertDialog(
        title: const Text('Экспорт данных'),
        content: SizedBox(
          width: 680,
          height: 420,
          child: SingleChildScrollView(child: SelectableText(json)),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Закрыть'),
          ),
          FilledButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: json));
              if (dialogContext.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('JSON скопирован')),
                );
              }
            },
            icon: const Icon(Icons.copy_outlined),
            label: const Text('Копировать'),
          ),
        ],
      );
    },
  );
}

Future<ImportPayload?> showImportDialog({required BuildContext context}) {
  return showDialog<ImportPayload>(
    context: context,
    barrierDismissible: false,
    builder: (BuildContext dialogContext) {
      return const _ImportDialog();
    },
  );
}

Future<bool> showDeleteAllDialog({required BuildContext context}) async {
  final bool? result = await showDialog<bool>(
    context: context,
    builder: (BuildContext dialogContext) {
      return AlertDialog(
        title: const Text('Удалить все задачи?'),
        content: const Text(
          'Операция необратима. Перед удалением можно сделать экспорт JSON.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Удалить всё'),
          ),
        ],
      );
    },
  );
  return result ?? false;
}

final class ImportPayload {
  const ImportPayload({required this.json, required this.mode});

  final String json;
  final ImportMode mode;
}

class _ImportDialog extends StatefulWidget {
  const _ImportDialog();

  @override
  State<_ImportDialog> createState() => _ImportDialogState();
}

class _ImportDialogState extends State<_ImportDialog> {
  final TextEditingController _controller = TextEditingController();
  ImportMode _mode = ImportMode.merge;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final String value = _controller.text.trim();
    if (value.isEmpty) {
      return;
    }
    Navigator.of(context).pop(ImportPayload(json: value, mode: _mode));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Импорт данных'),
      content: SizedBox(
        width: 680,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(
              controller: _controller,
              minLines: 10,
              maxLines: 16,
              decoration: const InputDecoration(
                labelText: 'JSON',
                hintText: 'Вставьте экспортированный JSON',
                alignLabelWithHint: true,
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<ImportMode>(
              initialValue: _mode,
              decoration: const InputDecoration(labelText: 'Режим импорта'),
              items: ImportMode.values
                  .map((ImportMode value) {
                    return DropdownMenuItem<ImportMode>(
                      value: value,
                      child: Text(value.label),
                    );
                  })
                  .toList(growable: false),
              onChanged: (ImportMode? value) {
                if (value != null) {
                  setState(() => _mode = value);
                }
              },
            ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Отмена'),
        ),
        FilledButton(onPressed: _submit, child: const Text('Импортировать')),
      ],
    );
  }
}
