import 'package:flutter/foundation.dart';

import '../../../core/id/task_id_generator.dart';
import '../data/finance_repository.dart';
import '../../planner/data/task_repository.dart';
import '../domain/finance_models.dart';

enum FinanceLoadState { loading, ready, error }

final class FinanceViewModel extends ChangeNotifier {
  FinanceViewModel({
    required FinanceRepository repository,
    required TaskIdGenerator idGenerator,
    DateTime Function()? now,
  }) : _repository = repository,
       _idGenerator = idGenerator,
       _now = now ?? DateTime.now;

  final FinanceRepository _repository;
  final TaskIdGenerator _idGenerator;
  final DateTime Function() _now;
  FinanceSnapshot? _snapshot;
  FinanceLoadState _loadState = FinanceLoadState.loading;
  bool _saving = false;
  bool _syncing = false;
  String? _error;

  FinanceLoadState get loadState => _loadState;
  bool get isSaving => _saving;
  String? get errorMessage => _error;
  FinanceSnapshot? get snapshot => _snapshot;
  List<FinanceAccountBalance> get accounts => _snapshot?.accounts ?? const [];
  List<FinanceCategory> get categories => _snapshot?.categories ?? const [];

  Future<void> initialize() async {
    _loadState = FinanceLoadState.loading;
    _error = null;
    notifyListeners();
    try {
      _snapshot = await _repository.loadSnapshot();
      _loadState = FinanceLoadState.ready;
    } catch (error, stack) {
      debugPrint('Finance initialization failed: $error\n$stack');
      _error = 'Не удалось загрузить финансовые данные.';
      _loadState = FinanceLoadState.error;
    }
    notifyListeners();
  }

  Future<void> synchronize() async {
    if (_syncing || _saving || _loadState != FinanceLoadState.ready) return;
    _syncing = true;
    try {
      _snapshot = await _repository.loadSnapshot();
      notifyListeners();
    } catch (_) {
      // Фоновая синхронизация не должна ломать текущий экран.
    } finally {
      _syncing = false;
    }
  }

  Future<void> _mutate(Future<void> Function() action) async {
    if (_saving) return;
    _saving = true;
    _error = null;
    notifyListeners();
    try {
      await action();
    } on Object catch (error, stack) {
      debugPrint('Finance operation failed: $error\n$stack');
      _error = _operationErrorMessage(error);
      _saving = false;
      notifyListeners();
      return;
    }
    try {
      _snapshot = await _repository.loadSnapshot();
    } on Object catch (error, stack) {
      debugPrint('Finance refresh after save failed: $error\n$stack');
      _error =
          'Изменение сохранено, но обновить экран не удалось. Данные появятся после синхронизации.';
    } finally {
      _saving = false;
      notifyListeners();
    }
  }

  void clearError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  String _operationErrorMessage(Object error) {
    if (error is TaskRepositoryException) {
      return switch (error.statusCode) {
        403 =>
          'Изменение финансов недоступно: проверьте подписку или права доступа.',
        409 => 'Данные уже изменились. Обновите страницу и повторите действие.',
        422 => error.message,
        429 => 'Достигнут лимит операций текущего тарифа.',
        _ =>
          'Не удалось сохранить изменение. Проверьте соединение и повторите попытку.',
      };
    }
    return 'Не удалось сохранить изменение. Повторите попытку.';
  }

  Future<void> addAccount({
    required String name,
    required int openingBalanceCents,
    required String colorHex,
    bool makeDefault = false,
  }) async {
    final now = _now().toUtc();
    await _mutate(() async {
      await _repository.createAccount(
        FinanceAccount(
          id: _idGenerator.next(),
          name: name.trim(),
          openingBalanceCents: openingBalanceCents,
          colorHex: colorHex,
          isDefault: makeDefault || accounts.isEmpty,
          isArchived: false,
          createdAt: now,
          updatedAt: now,
        ),
      );
    });
  }

  Future<void> addCategory({
    required String name,
    required String colorHex,
  }) async {
    final now = _now().toUtc();
    await _mutate(() async {
      await _repository.createCategory(
        FinanceCategory(
          id: _idGenerator.next(),
          name: name.trim(),
          colorHex: colorHex,
          icon: 'category',
          isSystem: false,
          createdAt: now,
          updatedAt: now,
        ),
      );
    });
  }

  Future<void> addTransaction({
    required FinanceTransactionType type,
    required int amountCents,
    required String accountId,
    String? toAccountId,
    String? categoryId,
    String note = '',
    DateTime? occurredAt,
  }) async {
    final now = _now().toUtc();
    await _mutate(() async {
      await _repository.createTransaction(
        FinanceTransaction(
          id: _idGenerator.next(),
          type: type,
          amountCents: amountCents,
          accountId: accountId,
          // A destination account belongs only to a transfer. Keeping this invariant
          // here protects every caller, not just the web dialog.
          toAccountId: type == FinanceTransactionType.transfer
              ? toAccountId
              : null,
          categoryId: type == FinanceTransactionType.transfer
              ? null
              : categoryId,
          note: note.trim(),
          occurredAt: occurredAt == null
              ? _now().toUtc()
              : DateTime.utc(
                  occurredAt.year,
                  occurredAt.month,
                  occurredAt.day,
                  12,
                ),
          createdAt: now,
        ),
      );
    });
  }

  Future<void> deleteTransaction(String id) =>
      _mutate(() => _repository.deleteTransaction(id));

  Future<void> addGoal({
    required String title,
    required int targetCents,
    int savedCents = 0,
    DateTime? dueDate,
    String? linkedAccountId,
  }) async {
    final now = _now().toUtc();
    await _mutate(() async {
      await _repository.createFinancialGoal(
        FinancialGoal(
          id: _idGenerator.next(),
          title: title.trim(),
          targetCents: targetCents,
          savedCents: savedCents,
          dueDate: dueDate,
          linkedAccountId: linkedAccountId,
          createdAt: now,
          updatedAt: now,
        ),
      );
    });
  }

  Future<void> addToGoal(FinancialGoal goal, int amountCents) async {
    if (goal.linkedAccountId != null || amountCents <= 0) return;
    await _mutate(
      () => _repository.updateFinancialGoal(
        FinancialGoal(
          id: goal.id,
          title: goal.title,
          targetCents: goal.targetCents,
          savedCents: goal.savedCents + amountCents,
          dueDate: goal.dueDate,
          linkedAccountId: goal.linkedAccountId,
          createdAt: goal.createdAt,
          updatedAt: _now().toUtc(),
        ),
      ),
    );
  }

  Future<void> addPayment({
    required String title,
    required int amountCents,
    required DateTime dueDate,
    required FinanceRecurrence recurrence,
    String? accountId,
    String? categoryId,
    bool createCalendarTask = true,
  }) async {
    final now = _now().toUtc();
    await _mutate(() async {
      await _repository.createPayment(
        FinancePayment(
          id: _idGenerator.next(),
          title: title.trim(),
          amountCents: amountCents,
          dueDate: dueDate,
          recurrence: recurrence,
          recurrenceDay: dueDate.day,
          accountId: accountId,
          categoryId: categoryId,
          isActive: true,
          createCalendarTask: createCalendarTask,
          createdAt: now,
          updatedAt: now,
        ),
      );
    });
  }

  Future<void> payPayment(FinancePayment payment) async {
    if (accounts.isEmpty) return;
    await _mutate(() => _repository.settlePayment(payment, _now().toUtc()));
  }

  Future<void> addDebt({
    required String title,
    required String person,
    required FinanceDebtDirection direction,
    required int amountCents,
    DateTime? dueDate,
    String note = '',
  }) async {
    final now = _now().toUtc();
    await _mutate(() async {
      await _repository.createDebt(
        FinanceDebt(
          id: _idGenerator.next(),
          title: title.trim(),
          person: person.trim(),
          direction: direction,
          amountCents: amountCents,
          dueDate: dueDate,
          status: FinanceDebtStatus.open,
          note: note.trim(),
          createdAt: now,
          updatedAt: now,
        ),
      );
    });
  }

  Future<void> settleDebt(FinanceDebt debt) async {
    await _mutate(
      () => _repository.updateDebt(
        FinanceDebt(
          id: debt.id,
          title: debt.title,
          person: debt.person,
          direction: debt.direction,
          amountCents: debt.amountCents,
          dueDate: debt.dueDate,
          status: FinanceDebtStatus.settled,
          note: debt.note,
          createdAt: debt.createdAt,
          updatedAt: _now().toUtc(),
        ),
      ),
    );
  }
}
