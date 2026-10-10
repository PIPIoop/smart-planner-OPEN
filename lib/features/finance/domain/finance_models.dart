import 'package:flutter/material.dart';

enum FinanceTransactionType { expense, income, transfer }

enum FinanceRecurrence { once, monthly }

enum FinanceDebtDirection { owedToMe, iOwe }

enum FinanceDebtStatus { open, settled }

DateTime _date(String value) => DateTime.parse(value).toLocal();
String _iso(DateTime value) => value.toUtc().toIso8601String();

Color colorFromHex(String value) {
  final String normalized = value.replaceFirst('#', '');
  return Color(int.parse('FF$normalized', radix: 16));
}

int? parseRublesToCents(
  String raw, {
  bool allowZero = false,
  bool allowNegative = false,
}) {
  String normalized = raw
      .trim()
      .replaceAll('\u00A0', '')
      .replaceAll(' ', '')
      .replaceAll(',', '.');
  if (normalized.isEmpty) {
    return allowZero ? 0 : null;
  }

  bool negative = false;
  if (normalized.startsWith('-')) {
    if (!allowNegative) {
      return null;
    }
    negative = true;
    normalized = normalized.substring(1);
  } else if (normalized.startsWith('+')) {
    normalized = normalized.substring(1);
  }

  final Match? match = RegExp(
    r'^(\d+)(?:\.(\d{1,2}))?$',
  ).firstMatch(normalized);
  if (match == null) {
    return null;
  }
  final int rubles = int.parse(match.group(1)!);
  final String fraction = match.group(2) ?? '';
  final int kopeks = fraction.isEmpty
      ? 0
      : int.parse(fraction.length == 1 ? '${fraction}0' : fraction);
  int cents = rubles * 100 + kopeks;
  if (negative) {
    cents = -cents;
  }
  if (!allowZero && cents == 0) {
    return null;
  }
  return cents;
}

String formatRubles(int cents) {
  final bool negative = cents < 0;
  final int absolute = cents.abs();
  final int rubles = absolute ~/ 100;
  final int kopeks = absolute % 100;
  final String digits = rubles.toString();
  final StringBuffer grouped = StringBuffer();
  for (int i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) {
      grouped.write(' ');
    }
    grouped.write(digits[i]);
  }
  final String fraction = kopeks == 0
      ? ''
      : ',${kopeks.toString().padLeft(2, '0')}';
  return '${negative ? '−' : ''}$grouped$fraction ₽';
}

class FinanceAccount {
  const FinanceAccount({
    required this.id,
    required this.name,
    required this.openingBalanceCents,
    required this.colorHex,
    required this.isDefault,
    required this.isArchived,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String name;
  final int openingBalanceCents;
  final String colorHex;
  final bool isDefault;
  final bool isArchived;
  final DateTime createdAt;
  final DateTime updatedAt;

  Color get color => colorFromHex(colorHex);

  factory FinanceAccount.fromJson(Map<String, Object?> json) => FinanceAccount(
    id: json['id']! as String,
    name: json['name']! as String,
    openingBalanceCents: json['openingBalanceCents']! as int,
    colorHex: json['colorHex']! as String,
    isDefault: json['isDefault']! as bool,
    isArchived: json['isArchived']! as bool,
    createdAt: _date(json['createdAt']! as String),
    updatedAt: _date(json['updatedAt']! as String),
  );

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'name': name,
    'openingBalanceCents': openingBalanceCents,
    'colorHex': colorHex,
    'isDefault': isDefault,
    'isArchived': isArchived,
    'createdAt': _iso(createdAt),
    'updatedAt': _iso(updatedAt),
  };
}

class FinanceAccountBalance {
  const FinanceAccountBalance({
    required this.account,
    required this.balanceCents,
  });
  final FinanceAccount account;
  final int balanceCents;

  factory FinanceAccountBalance.fromJson(Map<String, Object?> json) =>
      FinanceAccountBalance(
        account: FinanceAccount.fromJson(
          json['account']! as Map<String, Object?>,
        ),
        balanceCents: json['balanceCents']! as int,
      );
}

class FinanceCategory {
  const FinanceCategory({
    required this.id,
    required this.name,
    required this.colorHex,
    required this.icon,
    required this.isSystem,
    required this.createdAt,
    required this.updatedAt,
  });
  final String id;
  final String name;
  final String colorHex;
  final String icon;
  final bool isSystem;
  final DateTime createdAt;
  final DateTime updatedAt;
  Color get color => colorFromHex(colorHex);

  factory FinanceCategory.fromJson(Map<String, Object?> json) =>
      FinanceCategory(
        id: json['id']! as String,
        name: json['name']! as String,
        colorHex: json['colorHex']! as String,
        icon: json['icon']! as String,
        isSystem: json['isSystem']! as bool,
        createdAt: _date(json['createdAt']! as String),
        updatedAt: _date(json['updatedAt']! as String),
      );

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'name': name,
    'colorHex': colorHex,
    'icon': icon,
    'isSystem': isSystem,
    'createdAt': _iso(createdAt),
    'updatedAt': _iso(updatedAt),
  };
}

class FinanceTransaction {
  const FinanceTransaction({
    required this.id,
    required this.type,
    required this.amountCents,
    required this.accountId,
    required this.toAccountId,
    required this.categoryId,
    required this.note,
    required this.occurredAt,
    required this.createdAt,
  });
  final String id;
  final FinanceTransactionType type;
  final int amountCents;
  final String accountId;
  final String? toAccountId;
  final String? categoryId;
  final String note;
  final DateTime occurredAt;
  final DateTime createdAt;

  factory FinanceTransaction.fromJson(Map<String, Object?> json) =>
      FinanceTransaction(
        id: json['id']! as String,
        type: FinanceTransactionType.values.byName(json['type']! as String),
        amountCents: json['amountCents']! as int,
        accountId: json['accountId']! as String,
        toAccountId: json['toAccountId'] as String?,
        categoryId: json['categoryId'] as String?,
        note: json['note']! as String,
        occurredAt: _date(json['occurredAt']! as String),
        createdAt: _date(json['createdAt']! as String),
      );

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'type': type.name,
    'amountCents': amountCents,
    'accountId': accountId,
    // Keep the wire format valid even if a caller accidentally leaves a
    // destination selected while switching from transfer to expense/income.
    'toAccountId': type == FinanceTransactionType.transfer ? toAccountId : null,
    'categoryId': type == FinanceTransactionType.transfer ? null : categoryId,
    'note': note,
    'occurredAt': _iso(occurredAt), 'createdAt': _iso(createdAt),
  };
}

class FinancialGoal {
  const FinancialGoal({
    required this.id,
    required this.title,
    required this.targetCents,
    required this.savedCents,
    required this.dueDate,
    required this.linkedAccountId,
    required this.createdAt,
    required this.updatedAt,
  });
  final String id;
  final String title;
  final int targetCents;
  final int savedCents;
  final DateTime? dueDate;
  final String? linkedAccountId;
  final DateTime createdAt;
  final DateTime updatedAt;
  double get progress =>
      targetCents <= 0 ? 0 : (savedCents / targetCents).clamp(0, 1).toDouble();
  factory FinancialGoal.fromJson(Map<String, Object?> json) => FinancialGoal(
    id: json['id']! as String,
    title: json['title']! as String,
    targetCents: json['targetCents']! as int,
    savedCents: json['savedCents']! as int,
    dueDate: json['dueDate'] == null
        ? null
        : DateTime.parse(json['dueDate']! as String),
    linkedAccountId: json['linkedAccountId'] as String?,
    createdAt: _date(json['createdAt']! as String),
    updatedAt: _date(json['updatedAt']! as String),
  );
  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'title': title,
    'targetCents': targetCents,
    'savedCents': savedCents,
    'dueDate': dueDate == null
        ? null
        : '${dueDate!.year.toString().padLeft(4, '0')}-${dueDate!.month.toString().padLeft(2, '0')}-${dueDate!.day.toString().padLeft(2, '0')}',
    'linkedAccountId': linkedAccountId,
    'createdAt': _iso(createdAt),
    'updatedAt': _iso(updatedAt),
  };
}

class FinancePayment {
  const FinancePayment({
    required this.id,
    required this.title,
    required this.amountCents,
    required this.dueDate,
    required this.recurrence,
    required this.recurrenceDay,
    required this.accountId,
    required this.categoryId,
    required this.isActive,
    required this.createCalendarTask,
    required this.createdAt,
    required this.updatedAt,
  });
  final String id;
  final String title;
  final int amountCents;
  final DateTime dueDate;
  final FinanceRecurrence recurrence;
  final int recurrenceDay;
  final String? accountId;
  final String? categoryId;
  final bool isActive;
  final bool createCalendarTask;
  final DateTime createdAt;
  final DateTime updatedAt;
  factory FinancePayment.fromJson(Map<String, Object?> json) => FinancePayment(
    id: json['id']! as String,
    title: json['title']! as String,
    amountCents: json['amountCents']! as int,
    dueDate: DateTime.parse(json['dueDate']! as String),
    recurrence: FinanceRecurrence.values.byName(json['recurrence']! as String),
    recurrenceDay:
        json['recurrenceDay'] as int? ??
        DateTime.parse(json['dueDate']! as String).day,
    accountId: json['accountId'] as String?,
    categoryId: json['categoryId'] as String?,
    isActive: json['isActive']! as bool,
    createCalendarTask: json['createCalendarTask']! as bool,
    createdAt: _date(json['createdAt']! as String),
    updatedAt: _date(json['updatedAt']! as String),
  );
  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'title': title,
    'amountCents': amountCents,
    'dueDate':
        '${dueDate.year.toString().padLeft(4, '0')}-${dueDate.month.toString().padLeft(2, '0')}-${dueDate.day.toString().padLeft(2, '0')}',
    'recurrence': recurrence.name,
    'recurrenceDay': recurrenceDay,
    'accountId': accountId,
    'categoryId': categoryId,
    'isActive': isActive,
    'createCalendarTask': createCalendarTask,
    'createdAt': _iso(createdAt),
    'updatedAt': _iso(updatedAt),
  };
}

class FinanceDebt {
  const FinanceDebt({
    required this.id,
    required this.title,
    required this.person,
    required this.direction,
    required this.amountCents,
    required this.dueDate,
    required this.status,
    required this.note,
    required this.createdAt,
    required this.updatedAt,
  });
  final String id;
  final String title;
  final String person;
  final FinanceDebtDirection direction;
  final int amountCents;
  final DateTime? dueDate;
  final FinanceDebtStatus status;
  final String note;
  final DateTime createdAt;
  final DateTime updatedAt;
  factory FinanceDebt.fromJson(Map<String, Object?> json) => FinanceDebt(
    id: json['id']! as String,
    title: json['title']! as String,
    person: json['person']! as String,
    direction: switch (json['direction']! as String) {
      'owed_to_me' => FinanceDebtDirection.owedToMe,
      _ => FinanceDebtDirection.iOwe,
    },
    amountCents: json['amountCents']! as int,
    dueDate: json['dueDate'] == null
        ? null
        : DateTime.parse(json['dueDate']! as String),
    status: FinanceDebtStatus.values.byName(json['status']! as String),
    note: json['note']! as String,
    createdAt: _date(json['createdAt']! as String),
    updatedAt: _date(json['updatedAt']! as String),
  );
  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'title': title,
    'person': person,
    'direction': direction == FinanceDebtDirection.owedToMe
        ? 'owed_to_me'
        : 'i_owe',
    'amountCents': amountCents,
    'dueDate': dueDate == null
        ? null
        : '${dueDate!.year.toString().padLeft(4, '0')}-${dueDate!.month.toString().padLeft(2, '0')}-${dueDate!.day.toString().padLeft(2, '0')}',
    'status': status.name,
    'note': note,
    'createdAt': _iso(createdAt),
    'updatedAt': _iso(updatedAt),
  };
}

class FinanceCategorySpend {
  const FinanceCategorySpend({
    required this.categoryId,
    required this.name,
    required this.colorHex,
    required this.amountCents,
  });
  final String? categoryId;
  final String name;
  final String colorHex;
  final int amountCents;
  Color get color => colorFromHex(colorHex);
  factory FinanceCategorySpend.fromJson(Map<String, Object?> json) =>
      FinanceCategorySpend(
        categoryId: json['categoryId'] as String?,
        name: json['name']! as String,
        colorHex: json['colorHex']! as String,
        amountCents: json['amountCents']! as int,
      );
}

class FinanceDailySpend {
  const FinanceDailySpend({required this.date, required this.amountCents});
  final DateTime date;
  final int amountCents;
  factory FinanceDailySpend.fromJson(Map<String, Object?> json) =>
      FinanceDailySpend(
        date: DateTime.parse(json['date']! as String),
        amountCents: json['amountCents']! as int,
      );
}

class FinanceSnapshot {
  const FinanceSnapshot({
    required this.totalBalanceCents,
    required this.monthExpenseCents,
    required this.previousMonthExpenseCents,
    required this.todayExpenseCents,
    required this.averageDailyExpenseCents,
    required this.accounts,
    required this.categories,
    required this.categorySpend,
    required this.dailySpend,
    required this.goals,
    required this.payments,
    required this.debts,
    required this.recentTransactions,
  });
  final int totalBalanceCents;
  final int monthExpenseCents;
  final int previousMonthExpenseCents;
  final int todayExpenseCents;
  final int averageDailyExpenseCents;
  final List<FinanceAccountBalance> accounts;
  final List<FinanceCategory> categories;
  final List<FinanceCategorySpend> categorySpend;
  final List<FinanceDailySpend> dailySpend;
  final List<FinancialGoal> goals;
  final List<FinancePayment> payments;
  final List<FinanceDebt> debts;
  final List<FinanceTransaction> recentTransactions;
  factory FinanceSnapshot.fromSummaryJson(
    Map<String, Object?> json, {
    required List<FinanceCategory> categories,
  }) => FinanceSnapshot(
    totalBalanceCents: json['totalBalanceCents']! as int,
    monthExpenseCents: json['monthExpenseCents']! as int,
    previousMonthExpenseCents: json['previousMonthExpenseCents']! as int,
    todayExpenseCents: json['todayExpenseCents']! as int,
    averageDailyExpenseCents: json['averageDailyExpenseCents']! as int,
    accounts: (json['accounts']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinanceAccountBalance.fromJson)
        .toList(),
    categories: categories,
    categorySpend: (json['categorySpend']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinanceCategorySpend.fromJson)
        .toList(),
    dailySpend: (json['dailySpend']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinanceDailySpend.fromJson)
        .toList(),
    goals: (json['goals']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinancialGoal.fromJson)
        .toList(),
    payments: (json['payments']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinancePayment.fromJson)
        .toList(),
    debts: (json['debts']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinanceDebt.fromJson)
        .toList(),
    recentTransactions: (json['recentTransactions']! as List<Object?>)
        .cast<Map<String, Object?>>()
        .map(FinanceTransaction.fromJson)
        .toList(),
  );
}
