import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/features/finance/domain/finance_models.dart';

void main() {
  test('finance snapshot decodes account shares and expense analytics', () {
    final categories = <FinanceCategory>[
      FinanceCategory.fromJson(<String, Object?>{
        'id': 'food',
        'name': 'Продукты',
        'colorHex': '#5B8FF9',
        'icon': 'shopping_basket',
        'isSystem': true,
        'createdAt': '2026-08-08T10:00:00Z',
        'updatedAt': '2026-08-08T10:00:00Z',
      }),
    ];

    final snapshot = FinanceSnapshot.fromSummaryJson(<String, Object?>{
      'totalBalanceCents': 8750000,
      'monthExpenseCents': 125000,
      'previousMonthExpenseCents': 100000,
      'todayExpenseCents': 125000,
      'averageDailyExpenseCents': 15625,
      'accounts': <Object?>[
        <String, Object?>{
          'account': <String, Object?>{
            'id': 'main',
            'name': 'Основная карта',
            'openingBalanceCents': 10000000,
            'colorHex': '#5B47F7',
            'isDefault': true,
            'isArchived': false,
            'createdAt': '2026-08-08T10:00:00Z',
            'updatedAt': '2026-08-08T10:00:00Z',
          },
          'balanceCents': 8750000,
        },
      ],
      'categorySpend': <Object?>[
        <String, Object?>{
          'categoryId': 'food',
          'name': 'Продукты',
          'colorHex': '#5B8FF9',
          'amountCents': 125000,
        },
      ],
      'dailySpend': <Object?>[
        <String, Object?>{'date': '2026-08-08', 'amountCents': 125000},
      ],
      'goals': <Object?>[],
      'payments': <Object?>[],
      'debts': <Object?>[],
      'recentTransactions': <Object?>[],
    }, categories: categories);

    expect(snapshot.totalBalanceCents, 8750000);
    expect(snapshot.accounts.single.account.name, 'Основная карта');
    expect(snapshot.categorySpend.single.name, 'Продукты');
    expect(formatRubles(snapshot.monthExpenseCents), '1 250 ₽');
  });

  test('debt direction preserves API wire format', () {
    final debt = FinanceDebt.fromJson(<String, Object?>{
      'id': 'debt-1',
      'title': 'За билеты',
      'person': 'Иван',
      'direction': 'owed_to_me',
      'amountCents': 250000,
      'dueDate': '2026-08-20',
      'status': 'open',
      'note': '',
      'createdAt': '2026-08-08T10:00:00Z',
      'updatedAt': '2026-08-08T10:00:00Z',
    });

    expect(debt.direction, FinanceDebtDirection.owedToMe);
    expect(debt.toJson()['direction'], 'owed_to_me');
  });
  test(
    'expense serialization never sends transfer-only destination account',
    () {
      final transaction = FinanceTransaction(
        id: 'expense-1',
        type: FinanceTransactionType.expense,
        amountCents: 10000,
        accountId: 'card',
        toAccountId: 'savings',
        categoryId: 'other',
        note: '',
        occurredAt: DateTime.utc(2026, 8, 8, 12),
        createdAt: DateTime.utc(2026, 8, 8, 12),
      );

      final json = transaction.toJson();
      expect(json['toAccountId'], isNull);
      expect(json['categoryId'], 'other');
    },
  );

  test('money parser and formatter preserve kopeks exactly', () {
    expect(parseRublesToCents('1 250,75'), 125075);
    expect(parseRublesToCents('0,5'), 50);
    expect(parseRublesToCents('100.05'), 10005);
    expect(parseRublesToCents('12,345'), isNull);
    expect(parseRublesToCents('-10,25', allowNegative: true), -1025);
    expect(formatRubles(125075), '1 250,75 ₽');
    expect(formatRubles(125000), '1 250 ₽');
    expect(formatRubles(-1025), '−10,25 ₽');
  });

  test('payment preserves original recurrence day across JSON', () {
    final payment = FinancePayment.fromJson(<String, Object?>{
      'id': 'rent',
      'title': 'Аренда',
      'amountCents': 1000000,
      'dueDate': '2027-02-28',
      'recurrence': 'monthly',
      'recurrenceDay': 31,
      'accountId': 'main',
      'categoryId': 'housing',
      'isActive': true,
      'createCalendarTask': true,
      'createdAt': '2027-01-01T10:00:00Z',
      'updatedAt': '2027-01-31T10:00:00Z',
    });

    expect(payment.recurrenceDay, 31);
    expect(payment.toJson()['recurrenceDay'], 31);
  });
}
