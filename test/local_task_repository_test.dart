import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:smart_planner/features/finance/domain/finance_models.dart';
import 'package:smart_planner/features/planner/data/local_task_repository.dart';
import 'package:smart_planner/features/planner/domain/task_group.dart';

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  test('parallel local mutations preserve every group and account', () async {
    final LocalTaskRepository repository = LocalTaskRepository(
      preferences: SharedPreferencesAsync(),
    );
    final DateTime now = DateTime.utc(2026, 8, 12);

    await Future.wait(<Future<TaskGroup>>[
      repository.createGroup(
        TaskGroup.create(
          id: 'work',
          draft: TaskGroupDraft(name: 'Работа', colorHex: '#4F46E5'),
          now: now,
        ),
      ),
      repository.createGroup(
        TaskGroup.create(
          id: 'health',
          draft: TaskGroupDraft(name: 'Здоровье', colorHex: '#10B981'),
          now: now,
        ),
      ),
    ]);

    expect(
      (await repository.loadGroups()).map((TaskGroup group) => group.id),
      containsAll(<String>['work', 'health']),
    );

    FinanceAccount account(String id, String name, bool isDefault) =>
        FinanceAccount(
          id: id,
          name: name,
          openingBalanceCents: 0,
          colorHex: '#4F46E5',
          isDefault: isDefault,
          isArchived: false,
          createdAt: now,
          updatedAt: now,
        );

    await Future.wait(<Future<FinanceAccount>>[
      repository.createAccount(account('cash', 'Наличные', true)),
      repository.createAccount(account('card', 'Карта', false)),
    ]);

    final FinanceSnapshot snapshot = await repository.loadSnapshot();
    expect(
      snapshot.accounts.map(
        (FinanceAccountBalance balance) => balance.account.id,
      ),
      containsAll(<String>['cash', 'card']),
    );
  });
}
