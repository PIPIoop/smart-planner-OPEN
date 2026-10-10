import 'package:flutter/material.dart';

import '../../application/finance_view_model.dart';
import '../../domain/finance_models.dart';

void _showMoneyInputError(BuildContext context) {
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(
      content: Text(
        'Введите корректную сумму: например 1250,75. Допускается не более двух знаков после запятой.',
      ),
    ),
  );
}

Future<void> showAddAccountDialog(
  BuildContext context,
  FinanceViewModel vm,
) async {
  final name = TextEditingController();
  final balance = TextEditingController(text: '0');
  String color = '#5B47F7';
  bool makeDefault = vm.accounts.isEmpty;
  final saved = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Новый счёт'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Название счёта',
                  hintText: 'Например, Основная карта',
                ),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: balance,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                  signed: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Текущий остаток, ₽',
                ),
              ),
              const SizedBox(height: 14),
              DropdownButtonFormField<String>(
                initialValue: color,
                decoration: const InputDecoration(labelText: 'Цвет'),
                items: const [
                  DropdownMenuItem(value: '#5B47F7', child: Text('Фиолетовый')),
                  DropdownMenuItem(value: '#2F7CF6', child: Text('Синий')),
                  DropdownMenuItem(value: '#21B657', child: Text('Зелёный')),
                  DropdownMenuItem(value: '#F29D38', child: Text('Оранжевый')),
                  DropdownMenuItem(value: '#E45B72', child: Text('Розовый')),
                ],
                onChanged: (v) => setState(() => color = v ?? color),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: makeDefault,
                onChanged: (v) => setState(() => makeDefault = v ?? false),
                title: const Text('Использовать по умолчанию'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Создать счёт'),
          ),
        ],
      ),
    ),
  );
  if (saved == true && context.mounted && name.text.trim().isNotEmpty) {
    final int? cents = parseRublesToCents(
      balance.text,
      allowZero: true,
      allowNegative: true,
    );
    if (cents == null) {
      _showMoneyInputError(context);
    } else {
      await vm.addAccount(
        name: name.text,
        openingBalanceCents: cents,
        colorHex: color,
        makeDefault: makeDefault,
      );
    }
  }
  name.dispose();
  balance.dispose();
}

Future<void> showAddTransactionDialog(
  BuildContext context,
  FinanceViewModel vm, {
  FinanceTransactionType initialType = FinanceTransactionType.expense,
}) async {
  if (vm.accounts.isEmpty) {
    await showAddAccountDialog(context, vm);
    if (!context.mounted || vm.accounts.isEmpty) return;
  }
  final amount = TextEditingController();
  final note = TextEditingController();
  FinanceTransactionType type = initialType;
  String accountId = vm.accounts
      .firstWhere((a) => a.account.isDefault, orElse: () => vm.accounts.first)
      .account
      .id;
  String? toAccountId =
      vm.accounts.where((a) => a.account.id != accountId).isEmpty
      ? null
      : vm.accounts.firstWhere((a) => a.account.id != accountId).account.id;
  String? categoryId = vm.categories.isEmpty ? null : vm.categories.first.id;
  DateTime occurredAt = DateTime.now();
  final saved = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Новая операция'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SegmentedButton<FinanceTransactionType>(
                  segments: const [
                    ButtonSegment(
                      value: FinanceTransactionType.expense,
                      label: Text('Расход'),
                      icon: Icon(Icons.south_east),
                    ),
                    ButtonSegment(
                      value: FinanceTransactionType.income,
                      label: Text('Доход'),
                      icon: Icon(Icons.north_east),
                    ),
                    ButtonSegment(
                      value: FinanceTransactionType.transfer,
                      label: Text('Перевод'),
                      icon: Icon(Icons.swap_horiz),
                    ),
                  ],
                  selected: {type},
                  onSelectionChanged: (s) => setState(() => type = s.first),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: amount,
                  autofocus: true,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Сумма, ₽',
                    prefixIcon: Icon(Icons.currency_ruble),
                  ),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: accountId,
                  decoration: InputDecoration(
                    labelText: type == FinanceTransactionType.transfer
                        ? 'Со счёта'
                        : 'Счёт',
                  ),
                  items: vm.accounts
                      .map(
                        (a) => DropdownMenuItem(
                          value: a.account.id,
                          child: Text(
                            '${a.account.name} · ${formatRubles(a.balanceCents)}',
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (v) => setState(() {
                    if (v != null) {
                      accountId = v;
                      if (toAccountId == v) {
                        toAccountId =
                            vm.accounts.where((a) => a.account.id != v).isEmpty
                            ? null
                            : vm.accounts
                                  .firstWhere((a) => a.account.id != v)
                                  .account
                                  .id;
                      }
                    }
                  }),
                ),
                if (type == FinanceTransactionType.transfer) ...[
                  const SizedBox(height: 14),
                  DropdownButtonFormField<String>(
                    key: ValueKey<String?>('$accountId:$toAccountId'),
                    initialValue: toAccountId,
                    decoration: const InputDecoration(labelText: 'На счёт'),
                    items: vm.accounts
                        .where((a) => a.account.id != accountId)
                        .map(
                          (a) => DropdownMenuItem(
                            value: a.account.id,
                            child: Text(a.account.name),
                          ),
                        )
                        .toList(),
                    onChanged: (v) => setState(() => toAccountId = v),
                  ),
                ] else if (type == FinanceTransactionType.expense) ...[
                  const SizedBox(height: 14),
                  DropdownButtonFormField<String>(
                    initialValue: categoryId,
                    decoration: const InputDecoration(labelText: 'Категория'),
                    items: vm.categories
                        .map(
                          (c) => DropdownMenuItem(
                            value: c.id,
                            child: Text(c.name),
                          ),
                        )
                        .toList(),
                    onChanged: (v) => setState(() => categoryId = v),
                  ),
                ],
                const SizedBox(height: 14),
                TextField(
                  controller: note,
                  decoration: const InputDecoration(
                    labelText: 'Комментарий',
                    hintText: 'Например, продукты на неделю',
                  ),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: () async {
                    final d = await showDatePicker(
                      context: ctx,
                      initialDate: occurredAt,
                      firstDate: DateTime(2020),
                      lastDate: DateTime(2100),
                    );
                    if (d != null) setState(() => occurredAt = d);
                  },
                  icon: const Icon(Icons.calendar_today_outlined),
                  label: Text(
                    '${occurredAt.day.toString().padLeft(2, '0')}.${occurredAt.month.toString().padLeft(2, '0')}.${occurredAt.year}',
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Добавить'),
          ),
        ],
      ),
    ),
  );
  final int? cents = parseRublesToCents(amount.text);
  if (saved == true && context.mounted) {
    if (cents == null) {
      _showMoneyInputError(context);
    } else if (type == FinanceTransactionType.transfer && toAccountId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Для перевода выберите счёт назначения.')),
      );
    } else {
      await vm.addTransaction(
        type: type,
        amountCents: cents,
        accountId: accountId,
        toAccountId: type == FinanceTransactionType.transfer
            ? toAccountId
            : null,
        categoryId: type == FinanceTransactionType.transfer ? null : categoryId,
        note: note.text,
        occurredAt: occurredAt,
      );
    }
  }
  amount.dispose();
  note.dispose();
}

Future<void> showAddFinancialGoalDialog(
  BuildContext context,
  FinanceViewModel vm,
) async {
  final title = TextEditingController();
  final target = TextEditingController();
  final savedAmount = TextEditingController(text: '0');
  DateTime? due;
  String? linked;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Финансовая цель'),
        content: SizedBox(
          width: 480,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: title,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Цель',
                  hintText: 'Например, Финансовая подушка',
                ),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: target,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Нужно накопить, ₽',
                ),
              ),
              const SizedBox(height: 14),
              DropdownButtonFormField<String?>(
                initialValue: linked,
                decoration: const InputDecoration(
                  labelText: 'Связать со счётом (необязательно)',
                ),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('Не связывать'),
                  ),
                  ...vm.accounts.map(
                    (a) => DropdownMenuItem<String?>(
                      value: a.account.id,
                      child: Text(a.account.name),
                    ),
                  ),
                ],
                onChanged: (v) => setState(() => linked = v),
              ),
              if (linked == null) ...[
                const SizedBox(height: 14),
                TextField(
                  controller: savedAmount,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Уже накоплено, ₽',
                  ),
                ),
              ],
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final d = await showDatePicker(
                    context: ctx,
                    initialDate:
                        due ?? DateTime.now().add(const Duration(days: 90)),
                    firstDate: DateTime.now(),
                    lastDate: DateTime(2100),
                  );
                  if (d != null) setState(() => due = d);
                },
                icon: const Icon(Icons.flag_outlined),
                label: Text(
                  due == null
                      ? 'Добавить срок'
                      : 'До ${due!.day}.${due!.month}.${due!.year}',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Создать'),
          ),
        ],
      ),
    ),
  );
  final tc = parseRublesToCents(target.text);
  final sc = parseRublesToCents(savedAmount.text, allowZero: true);
  if (ok == true && context.mounted && title.text.trim().isNotEmpty) {
    if (tc == null || sc == null) {
      _showMoneyInputError(context);
    } else {
      await vm.addGoal(
        title: title.text,
        targetCents: tc,
        savedCents: sc,
        dueDate: due,
        linkedAccountId: linked,
      );
    }
  }
  title.dispose();
  target.dispose();
  savedAmount.dispose();
}

Future<void> showAddPaymentDialog(
  BuildContext context,
  FinanceViewModel vm,
) async {
  final title = TextEditingController();
  final amount = TextEditingController();
  DateTime due = DateTime.now().add(const Duration(days: 7));
  FinanceRecurrence recurrence = FinanceRecurrence.monthly;
  String? accountId = vm.accounts.isEmpty ? null : vm.accounts.first.account.id;
  String? categoryId = vm.categories.isEmpty ? null : vm.categories.first.id;
  bool calendar = true;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Обязательный платёж'),
        content: SizedBox(
          width: 500,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: title,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: 'Название',
                    hintText: 'Например, Аренда',
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: amount,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(labelText: 'Сумма, ₽'),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<FinanceRecurrence>(
                  initialValue: recurrence,
                  decoration: const InputDecoration(labelText: 'Повтор'),
                  items: const [
                    DropdownMenuItem(
                      value: FinanceRecurrence.monthly,
                      child: Text('Каждый месяц'),
                    ),
                    DropdownMenuItem(
                      value: FinanceRecurrence.once,
                      child: Text('Один раз'),
                    ),
                  ],
                  onChanged: (v) =>
                      setState(() => recurrence = v ?? recurrence),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String?>(
                  initialValue: accountId,
                  decoration: const InputDecoration(labelText: 'Счёт'),
                  items: [
                    const DropdownMenuItem<String?>(
                      value: null,
                      child: Text('Не выбран'),
                    ),
                    ...vm.accounts.map(
                      (a) => DropdownMenuItem<String?>(
                        value: a.account.id,
                        child: Text(a.account.name),
                      ),
                    ),
                  ],
                  onChanged: (v) => setState(() => accountId = v),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String?>(
                  initialValue: categoryId,
                  decoration: const InputDecoration(labelText: 'Категория'),
                  items: [
                    const DropdownMenuItem<String?>(
                      value: null,
                      child: Text('Без категории'),
                    ),
                    ...vm.categories.map(
                      (c) => DropdownMenuItem<String?>(
                        value: c.id,
                        child: Text(c.name),
                      ),
                    ),
                  ],
                  onChanged: (v) => setState(() => categoryId = v),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: () async {
                    final d = await showDatePicker(
                      context: ctx,
                      initialDate: due,
                      firstDate: DateTime.now().subtract(
                        const Duration(days: 1),
                      ),
                      lastDate: DateTime(2100),
                    );
                    if (d != null) setState(() => due = d);
                  },
                  icon: const Icon(Icons.event_outlined),
                  label: Text('${due.day}.${due.month}.${due.year}'),
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: calendar,
                  onChanged: (v) => setState(() => calendar = v ?? true),
                  title: const Text('Показывать в календаре'),
                  subtitle: const Text(
                    'Создаст задачи-напоминания без автоматического списания денег',
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Добавить'),
          ),
        ],
      ),
    ),
  );
  final cents = parseRublesToCents(amount.text);
  if (ok == true && context.mounted && title.text.trim().isNotEmpty) {
    if (cents == null) {
      _showMoneyInputError(context);
    } else {
      await vm.addPayment(
        title: title.text,
        amountCents: cents,
        dueDate: due,
        recurrence: recurrence,
        accountId: accountId,
        categoryId: categoryId,
        createCalendarTask: calendar,
      );
    }
  }
  title.dispose();
  amount.dispose();
}

Future<void> showAddDebtDialog(
  BuildContext context,
  FinanceViewModel vm,
) async {
  final title = TextEditingController();
  final person = TextEditingController();
  final amount = TextEditingController();
  FinanceDebtDirection direction = FinanceDebtDirection.iOwe;
  DateTime? due;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Добавить долг'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SegmentedButton<FinanceDebtDirection>(
                segments: const [
                  ButtonSegment(
                    value: FinanceDebtDirection.iOwe,
                    label: Text('Я должен'),
                  ),
                  ButtonSegment(
                    value: FinanceDebtDirection.owedToMe,
                    label: Text('Мне должны'),
                  ),
                ],
                selected: {direction},
                onSelectionChanged: (s) => setState(() => direction = s.first),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: title,
                decoration: const InputDecoration(labelText: 'Описание'),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: person,
                decoration: const InputDecoration(
                  labelText: 'Человек / организация',
                ),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(labelText: 'Сумма, ₽'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final d = await showDatePicker(
                    context: ctx,
                    initialDate: DateTime.now().add(const Duration(days: 30)),
                    firstDate: DateTime.now(),
                    lastDate: DateTime(2100),
                  );
                  if (d != null) setState(() => due = d);
                },
                icon: const Icon(Icons.event_available_outlined),
                label: Text(
                  due == null
                      ? 'Без срока'
                      : 'До ${due!.day}.${due!.month}.${due!.year}',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Добавить'),
          ),
        ],
      ),
    ),
  );
  final cents = parseRublesToCents(amount.text);
  if (ok == true && context.mounted && title.text.trim().isNotEmpty) {
    if (cents == null) {
      _showMoneyInputError(context);
    } else {
      await vm.addDebt(
        title: title.text,
        person: person.text,
        direction: direction,
        amountCents: cents,
        dueDate: due,
      );
    }
  }
  title.dispose();
  person.dispose();
  amount.dispose();
}

Future<void> showAddGoalSavingsDialog(
  BuildContext context,
  FinanceViewModel vm,
  FinancialGoal goal,
) async {
  final controller = TextEditingController();
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text('Пополнить «${goal.title}»'),
      content: TextField(
        controller: controller,
        autofocus: true,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(labelText: 'Сумма, ₽'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Добавить'),
        ),
      ],
    ),
  );
  final cents = parseRublesToCents(controller.text);
  if (ok == true && context.mounted) {
    if (cents == null) {
      _showMoneyInputError(context);
    } else {
      await vm.addToGoal(goal, cents);
    }
  }
  controller.dispose();
}

Future<void> showAddCategoryDialog(
  BuildContext context,
  FinanceViewModel vm,
) async {
  final name = TextEditingController();
  String color = '#5B47F7';
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Новая категория'),
        content: SizedBox(
          width: 440,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Название',
                  hintText: 'Например, Кофе или Подарки',
                ),
              ),
              const SizedBox(height: 14),
              DropdownButtonFormField<String>(
                initialValue: color,
                decoration: const InputDecoration(labelText: 'Цвет'),
                items: const [
                  DropdownMenuItem(value: '#5B47F7', child: Text('Фиолетовый')),
                  DropdownMenuItem(value: '#2F7CF6', child: Text('Синий')),
                  DropdownMenuItem(value: '#21B657', child: Text('Зелёный')),
                  DropdownMenuItem(value: '#F29D38', child: Text('Оранжевый')),
                  DropdownMenuItem(value: '#E45B72', child: Text('Розовый')),
                ],
                onChanged: (value) => setState(() => color = value ?? color),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Создать'),
          ),
        ],
      ),
    ),
  );
  if (ok == true && context.mounted && name.text.trim().isNotEmpty) {
    await vm.addCategory(name: name.text, colorHex: color);
  }
  name.dispose();
}
