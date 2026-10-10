import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/core/id/task_id_generator.dart';
import 'package:smart_planner/features/finance/application/finance_view_model.dart';
import 'package:smart_planner/features/finance/data/finance_repository.dart';
import 'package:smart_planner/features/finance/domain/finance_models.dart';
import 'package:smart_planner/features/finance/presentation/finance_page.dart';
import 'package:smart_planner/features/planner/data/task_repository.dart';

void main() {
  test('finance operation failure becomes a user-facing error', () async {
    final _FakeFinanceRepository repository = _FakeFinanceRepository();
    final FinanceViewModel viewModel = FinanceViewModel(
      repository: repository,
      idGenerator: TaskIdGenerator(),
    );
    await viewModel.initialize();
    repository.mutationError = const TaskRepositoryException(
      'Full subscription is required',
      statusCode: 403,
    );

    await viewModel.addAccount(
      name: 'Карта',
      openingBalanceCents: 100000,
      colorHex: '#5B47F7',
    );

    expect(viewModel.isSaving, isFalse);
    expect(
      viewModel.errorMessage,
      'Изменение финансов недоступно: проверьте подписку или права доступа.',
    );
  });

  test('failed refresh says that the preceding write was saved', () async {
    final _FakeFinanceRepository repository = _FakeFinanceRepository();
    final FinanceViewModel viewModel = FinanceViewModel(
      repository: repository,
      idGenerator: TaskIdGenerator(),
    );
    await viewModel.initialize();
    repository.failLoadAfterMutation = true;

    await viewModel.addAccount(
      name: 'Карта',
      openingBalanceCents: 100000,
      colorHex: '#5B47F7',
    );

    expect(repository.createAccountCalls, 1);
    expect(
      viewModel.errorMessage,
      'Изменение сохранено, но обновить экран не удалось. Данные появятся после синхронизации.',
    );
  });

  testWidgets('payment requires confirmation and uses one settlement call', (
    WidgetTester tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1280, 1100));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final _FakeFinanceRepository repository = _FakeFinanceRepository(
      snapshot: _snapshotWithPayment(),
    );
    final FinanceViewModel viewModel = FinanceViewModel(
      repository: repository,
      idGenerator: TaskIdGenerator(),
    );
    await viewModel.initialize();

    await tester.pumpWidget(
      MaterialApp(
        home: FinancePage(viewModel: viewModel, onOpenPlanner: () {}),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Оплачено'));
    await tester.pumpAndSettle();
    expect(find.text('Подтвердить оплату'), findsOneWidget);
    expect(find.textContaining('1 000 ₽'), findsWidgets);
    await tester.tap(find.text('Отмена'));
    await tester.pumpAndSettle();
    expect(repository.settleCalls, 0);

    await tester.tap(find.text('Оплачено'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Подтвердить'));
    await tester.pumpAndSettle();
    expect(repository.settleCalls, 1);
  });
}

FinanceSnapshot _emptySnapshot() => const FinanceSnapshot(
  totalBalanceCents: 0,
  monthExpenseCents: 0,
  previousMonthExpenseCents: 0,
  todayExpenseCents: 0,
  averageDailyExpenseCents: 0,
  accounts: <FinanceAccountBalance>[],
  categories: <FinanceCategory>[],
  categorySpend: <FinanceCategorySpend>[],
  dailySpend: <FinanceDailySpend>[],
  goals: <FinancialGoal>[],
  payments: <FinancePayment>[],
  debts: <FinanceDebt>[],
  recentTransactions: <FinanceTransaction>[],
);

FinanceSnapshot _snapshotWithPayment() {
  final DateTime timestamp = DateTime.utc(2027, 1, 1, 10);
  final FinanceAccount account = FinanceAccount(
    id: 'main',
    name: 'Карта',
    openingBalanceCents: 1000000,
    colorHex: '#5B47F7',
    isDefault: true,
    isArchived: false,
    createdAt: timestamp,
    updatedAt: timestamp,
  );
  return FinanceSnapshot(
    totalBalanceCents: 1000000,
    monthExpenseCents: 0,
    previousMonthExpenseCents: 0,
    todayExpenseCents: 0,
    averageDailyExpenseCents: 0,
    accounts: <FinanceAccountBalance>[
      FinanceAccountBalance(account: account, balanceCents: 1000000),
    ],
    categories: const <FinanceCategory>[],
    categorySpend: const <FinanceCategorySpend>[],
    dailySpend: const <FinanceDailySpend>[],
    goals: const <FinancialGoal>[],
    payments: <FinancePayment>[
      FinancePayment(
        id: 'rent',
        title: 'Аренда',
        amountCents: 100000,
        dueDate: DateTime(2027, 1, 31),
        recurrence: FinanceRecurrence.monthly,
        recurrenceDay: 31,
        accountId: 'main',
        categoryId: 'housing',
        isActive: true,
        createCalendarTask: true,
        createdAt: timestamp,
        updatedAt: timestamp,
      ),
    ],
    debts: const <FinanceDebt>[],
    recentTransactions: const <FinanceTransaction>[],
  );
}

final class _FakeFinanceRepository implements FinanceRepository {
  _FakeFinanceRepository({FinanceSnapshot? snapshot})
    : snapshot = snapshot ?? _emptySnapshot();

  FinanceSnapshot snapshot;
  Object? mutationError;
  bool failLoadAfterMutation = false;
  bool _mutated = false;
  int createAccountCalls = 0;
  int settleCalls = 0;

  void _checkMutation() {
    final Object? error = mutationError;
    if (error != null) throw error;
    _mutated = true;
  }

  @override
  Future<FinanceSnapshot> loadSnapshot() async {
    if (failLoadAfterMutation && _mutated) {
      throw StateError('refresh unavailable');
    }
    return snapshot;
  }

  @override
  Future<FinanceAccount> createAccount(FinanceAccount account) async {
    _checkMutation();
    createAccountCalls++;
    return account;
  }

  @override
  Future<FinanceAccount> updateAccount(FinanceAccount account) async {
    _checkMutation();
    return account;
  }

  @override
  Future<void> deleteAccount(String id) async => _checkMutation();

  @override
  Future<FinanceCategory> createCategory(FinanceCategory category) async {
    _checkMutation();
    return category;
  }

  @override
  Future<FinanceTransaction> createTransaction(
    FinanceTransaction transaction,
  ) async {
    _checkMutation();
    return transaction;
  }

  @override
  Future<void> deleteTransaction(String id) async => _checkMutation();

  @override
  Future<FinancialGoal> createFinancialGoal(FinancialGoal goal) async {
    _checkMutation();
    return goal;
  }

  @override
  Future<FinancialGoal> updateFinancialGoal(FinancialGoal goal) async {
    _checkMutation();
    return goal;
  }

  @override
  Future<void> deleteFinancialGoal(String id) async => _checkMutation();

  @override
  Future<FinancePayment> createPayment(FinancePayment payment) async {
    _checkMutation();
    return payment;
  }

  @override
  Future<FinancePayment> updatePayment(FinancePayment payment) async {
    _checkMutation();
    return payment;
  }

  @override
  Future<FinancePayment> settlePayment(
    FinancePayment payment,
    DateTime paidAt,
  ) async {
    _checkMutation();
    settleCalls++;
    return payment;
  }

  @override
  Future<void> deletePayment(String id) async => _checkMutation();

  @override
  Future<FinanceDebt> createDebt(FinanceDebt debt) async {
    _checkMutation();
    return debt;
  }

  @override
  Future<FinanceDebt> updateDebt(FinanceDebt debt) async {
    _checkMutation();
    return debt;
  }

  @override
  Future<void> deleteDebt(String id) async => _checkMutation();
}
