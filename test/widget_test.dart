import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/app.dart';
import 'package:smart_planner/core/id/task_id_generator.dart';
import 'package:smart_planner/features/planner/application/planner_view_model.dart';
import 'package:smart_planner/features/planner/domain/planner_user.dart';
import 'package:smart_planner/features/planner/domain/task_group.dart';

import 'support/fake_task_repository.dart';

void main() {
  testWidgets('planner renders redesigned desktop calendar', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);

    await tester.pumpWidget(SmartPlannerApp(viewModel: viewModel));
    await tester.pumpAndSettle();

    expect(find.text('Smart Planner'), findsOneWidget);
    expect(find.text('Август 2026'), findsOneWidget);
    expect(find.text('Обучение'), findsOneWidget);
    expect(find.byTooltip('Новая задача'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('planner-header')),
      findsOneWidget,
    );
    expect(find.byType(GridView), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('admin can select another isolated calendar', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);
    String? selected;

    await tester.pumpWidget(
      SmartPlannerApp(
        viewModel: viewModel,
        users: const <PlannerUser>[
          PlannerUser(
            id: '100',
            displayName: 'Администратор',
            username: 'admin',
            role: 'admin',
            status: 'active',
          ),
          PlannerUser(
            id: '200',
            displayName: 'Пользователь',
            role: 'user',
            status: 'active',
          ),
        ],
        selectedUserId: '100',
        onUserSelected: (String value) => selected = value,
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('user-calendar-selector')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('user-calendar-dropdown')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Пользователь').last);
    await tester.pumpAndSettle();
    expect(selected, '200');
    expect(tester.takeException(), isNull);
  });
  testWidgets('creates a task only after title validation', (
    WidgetTester tester,
  ) async {
    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);
    await tester.pumpWidget(SmartPlannerApp(viewModel: viewModel));

    await tester.tap(find.byTooltip('Новая задача'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Создать'));
    await tester.pump();
    expect(find.text('Введите название задачи'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).first, 'Купить продукты');
    await tester.tap(find.widgetWithText(FilledButton, 'Создать'));
    await tester.pumpAndSettle();

    expect(find.text('Купить продукты'), findsWidgets);
    expect(viewModel.tasks.single.title, 'Купить продукты');
  });

  testWidgets('creates a timed task with selected duration', (
    WidgetTester tester,
  ) async {
    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);
    await tester.pumpWidget(SmartPlannerApp(viewModel: viewModel));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Новая задача'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first, 'Рабочий блок');
    await tester.tap(find.text('Добавить время'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ОК'));
    await tester.pumpAndSettle();

    expect(find.text('Длительность'), findsOneWidget);
    await tester.tap(find.text('1 ч'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('2 ч').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Создать'));
    await tester.pumpAndSettle();

    expect(viewModel.tasks.single.startMinute, 9 * 60);
    expect(viewModel.tasks.single.durationMinutes, 120);
    expect(find.text('09:00–11:00'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
  testWidgets('assigns one colored group from the task form', (
    WidgetTester tester,
  ) async {
    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);
    await viewModel.createGroup(
      TaskGroupDraft(name: 'Работа', colorHex: '#14B8A6'),
    );
    await tester.pumpWidget(SmartPlannerApp(viewModel: viewModel));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Новая задача'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first, 'Задача группы');
    await tester.tap(find.text('Без группы'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Работа').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Создать'));
    await tester.pumpAndSettle();

    expect(viewModel.tasks.single.groupId, viewModel.groups.single.id);
    expect(find.text('Работа'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
  testWidgets('tutorial walks through all interface areas', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);
    await tester.pumpWidget(SmartPlannerApp(viewModel: viewModel));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Обучение'));
    await tester.pumpAndSettle();

    expect(find.text('Добро пожаловать'), findsOneWidget);
    expect(find.text('1 из 6'), findsOneWidget);

    for (final String title in _tutorialTitles) {
      await tester.tap(find.widgetWithText(FilledButton, 'Далее'));
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byKey(
            ValueKey<String>(
              'tutorial-step-${_tutorialTitles.indexOf(title) + 1}',
            ),
          ),
          matching: find.text(title),
        ),
        findsOneWidget,
      );
    }

    expect(find.text('6 из 6'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Готово'));
    await tester.pumpAndSettle();
    expect(find.text('Резервная копия'), findsNothing);
  });

  testWidgets('renders without overflow in a narrow viewport', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(480, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final PlannerViewModel viewModel = await _createViewModel();
    addTearDown(viewModel.dispose);
    await tester.pumpWidget(SmartPlannerApp(viewModel: viewModel));
    await tester.pumpAndSettle();

    expect(find.byType(GridView), findsOneWidget);
    expect(find.text('Обучение'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

const List<String> _tutorialTitles = <String>[
  'Поиск задач',
  'Календарь',
  'План выбранного дня',
  'Новая задача',
  'Резервная копия',
];

Future<PlannerViewModel> _createViewModel() async {
  final PlannerViewModel viewModel = PlannerViewModel(
    repository: FakeTaskRepository(),
    idGenerator: TaskIdGenerator(random: Random(1)),
    initialDate: DateTime(2026, 8, 2),
    now: () => DateTime(2026, 8, 2),
  );
  await viewModel.initialize();
  return viewModel;
}
