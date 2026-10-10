import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/features/planner/domain/task_group.dart';

void main() {
  test('normalizes group and converts pleasant palette colors', () {
    final TaskGroupDraft draft = TaskGroupDraft(
      name: '  Личная   жизнь ',
      colorHex: '#ec4899',
    );
    expect(draft.name, 'Личная жизнь');
    expect(draft.colorHex, '#EC4899');
    expect(colorFromHex(draft.colorHex).toARGB32(), 0xFFEC4899);
    expect(taskGroupColorPalette, hasLength(12));
  });

  test('rejects empty names and invalid colors', () {
    expect(
      () => TaskGroupDraft(name: ' ', colorHex: '#3B82F6'),
      throwsArgumentError,
    );
    expect(
      () => TaskGroupDraft(name: 'Работа', colorHex: 'blue'),
      throwsArgumentError,
    );
  });
}
