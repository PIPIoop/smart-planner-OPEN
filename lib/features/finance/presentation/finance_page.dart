import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../planner/domain/planner_user.dart';
import '../application/finance_view_model.dart';
import '../domain/finance_models.dart';
import 'dialogs/finance_dialogs.dart';

class FinancePage extends StatelessWidget {
  const FinancePage({
    required this.viewModel,
    required this.onOpenPlanner,
    this.onOpenAdmin,
    this.users = const <PlannerUser>[],
    this.selectedUserId,
    this.onUserSelected,
    this.readOnly = false,
    super.key,
  });

  final FinanceViewModel viewModel;
  final VoidCallback onOpenPlanner;
  final VoidCallback? onOpenAdmin;
  final List<PlannerUser> users;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: viewModel,
      builder: (context, _) => Scaffold(
        body: SafeArea(
          child: viewModel.loadState == FinanceLoadState.loading
              ? const Center(child: CircularProgressIndicator())
              : viewModel.loadState == FinanceLoadState.error
              ? _FinanceError(viewModel: viewModel)
              : _FinanceDashboard(
                  viewModel: viewModel,
                  onOpenPlanner: onOpenPlanner,
                  onOpenAdmin: onOpenAdmin,
                  users: users,
                  selectedUserId: selectedUserId,
                  onUserSelected: onUserSelected,
                  readOnly: readOnly,
                ),
        ),
      ),
    );
  }
}

class _FinanceOperationError extends StatelessWidget {
  const _FinanceOperationError({required this.message, required this.onClose});

  final String message;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    decoration: BoxDecoration(
      color: const Color(0xFFFFEEEE),
      borderRadius: BorderRadius.circular(13),
      border: Border.all(color: const Color(0xFFF1B9B9)),
    ),
    child: Row(
      children: [
        const Icon(Icons.error_outline, color: Color(0xFFB42318), size: 20),
        const SizedBox(width: 9),
        Expanded(
          child: Text(
            message,
            style: const TextStyle(
              color: Color(0xFF8A1C15),
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        IconButton(
          tooltip: 'Закрыть сообщение',
          onPressed: onClose,
          icon: const Icon(Icons.close, size: 18),
        ),
      ],
    ),
  );
}

class _FinanceError extends StatelessWidget {
  const _FinanceError({required this.viewModel});
  final FinanceViewModel viewModel;
  @override
  Widget build(BuildContext context) => Center(
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.account_balance_wallet_outlined,
              size: 48,
              color: Color(0xFF5B47F7),
            ),
            const SizedBox(height: 12),
            Text(viewModel.errorMessage ?? 'Не удалось загрузить финансы'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: viewModel.initialize,
              child: const Text('Повторить'),
            ),
          ],
        ),
      ),
    ),
  );
}

class _FinanceDashboard extends StatelessWidget {
  const _FinanceDashboard({
    required this.viewModel,
    required this.onOpenPlanner,
    required this.onOpenAdmin,
    required this.users,
    required this.selectedUserId,
    required this.onUserSelected,
    required this.readOnly,
  });
  final FinanceViewModel viewModel;
  final VoidCallback onOpenPlanner;
  final VoidCallback? onOpenAdmin;
  final List<PlannerUser> users;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;
  final bool readOnly;

  FinanceSnapshot get data => viewModel.snapshot!;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final bool compact = constraints.maxWidth < 980;
        final Widget editableContent = data.accounts.isEmpty
            ? _EmptyFinance(
                onCreateAccount: () => showAddAccountDialog(context, viewModel),
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (compact) ...[
                    _BalanceCard(
                      data: data,
                      onAddAccount: () =>
                          showAddAccountDialog(context, viewModel),
                    ),
                    const SizedBox(height: 14),
                    _ExpenseSummary(data: data),
                  ] else
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          flex: 7,
                          child: _BalanceCard(
                            data: data,
                            onAddAccount: () =>
                                showAddAccountDialog(context, viewModel),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(flex: 5, child: _ExpenseSummary(data: data)),
                      ],
                    ),
                  const SizedBox(height: 14),
                  if (compact) ...[
                    _SpendingTrendCard(data: data),
                    const SizedBox(height: 14),
                    _CategoriesCard(
                      data: data,
                      onAdd: () => showAddCategoryDialog(context, viewModel),
                    ),
                  ] else
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          flex: 7,
                          child: _SpendingTrendCard(data: data),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          flex: 5,
                          child: _CategoriesCard(
                            data: data,
                            onAdd: () =>
                                showAddCategoryDialog(context, viewModel),
                          ),
                        ),
                      ],
                    ),
                  const SizedBox(height: 14),
                  _QuickActions(viewModel: viewModel),
                  const SizedBox(height: 14),
                  if (compact) ...[
                    _GoalsCard(
                      data: data,
                      viewModel: viewModel,
                      onAdd: () =>
                          showAddFinancialGoalDialog(context, viewModel),
                    ),
                    const SizedBox(height: 14),
                    _PaymentsCard(
                      data: data,
                      viewModel: viewModel,
                      onAdd: () => showAddPaymentDialog(context, viewModel),
                    ),
                    const SizedBox(height: 14),
                    _DebtsCard(
                      data: data,
                      viewModel: viewModel,
                      onAdd: () => showAddDebtDialog(context, viewModel),
                    ),
                  ] else
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: _GoalsCard(
                            data: data,
                            viewModel: viewModel,
                            onAdd: () =>
                                showAddFinancialGoalDialog(context, viewModel),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: _PaymentsCard(
                            data: data,
                            viewModel: viewModel,
                            onAdd: () =>
                                showAddPaymentDialog(context, viewModel),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: _DebtsCard(
                            data: data,
                            viewModel: viewModel,
                            onAdd: () => showAddDebtDialog(context, viewModel),
                          ),
                        ),
                      ],
                    ),
                  const SizedBox(height: 14),
                  _RecentTransactions(data: data, viewModel: viewModel),
                ],
              );

        return SingleChildScrollView(
          padding: EdgeInsets.all(compact ? 12 : 18),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1540),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _FinanceHeader(
                    onOpenPlanner: onOpenPlanner,
                    onOpenAdmin: onOpenAdmin,
                    onAddExpense: readOnly
                        ? null
                        : () => showAddTransactionDialog(context, viewModel),
                    users: users,
                    selectedUserId: selectedUserId,
                    onUserSelected: onUserSelected,
                  ),
                  if (readOnly) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 15,
                        vertical: 11,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF7E8),
                        borderRadius: BorderRadius.circular(13),
                        border: Border.all(color: const Color(0xFFF0D7A4)),
                      ),
                      child: const Row(
                        children: [
                          Icon(
                            Icons.visibility_outlined,
                            color: Color(0xFF9B6500),
                            size: 20,
                          ),
                          SizedBox(width: 9),
                          Expanded(
                            child: Text(
                              'Режим администратора · только просмотр. Финансовые данные нельзя изменять.',
                              style: TextStyle(
                                color: Color(0xFF72500D),
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                  if (viewModel.errorMessage case final String message) ...[
                    const SizedBox(height: 12),
                    _FinanceOperationError(
                      message: message,
                      onClose: viewModel.clearError,
                    ),
                  ],
                  const SizedBox(height: 16),
                  IgnorePointer(ignoring: readOnly, child: editableContent),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _FinanceHeader extends StatelessWidget {
  const _FinanceHeader({
    required this.onOpenPlanner,
    required this.onOpenAdmin,
    required this.onAddExpense,
    required this.users,
    required this.selectedUserId,
    required this.onUserSelected,
  });
  final VoidCallback onOpenPlanner;
  final VoidCallback? onOpenAdmin;
  final VoidCallback? onAddExpense;
  final List<PlannerUser> users;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: const Color(0xFFE8EBF2)),
    ),
    child: LayoutBuilder(
      builder: (context, c) {
        final bool narrow = c.maxWidth < 920;
        final logo = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: const Color(0xFFF0EEFF),
                borderRadius: BorderRadius.circular(11),
              ),
              child: const Icon(
                Icons.account_balance_wallet_outlined,
                color: Color(0xFF5546F7),
              ),
            ),
            const SizedBox(width: 12),
            const Text(
              'Smart Planner',
              style: TextStyle(fontWeight: FontWeight.w900, fontSize: 17),
            ),
          ],
        );
        final nav = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextButton.icon(
              onPressed: onOpenPlanner,
              icon: const Icon(Icons.calendar_today_outlined, size: 18),
              label: const Text('Календарь'),
              style: TextButton.styleFrom(
                foregroundColor: const Color(0xFF30364A),
              ),
            ),
            const SizedBox(width: 4),
            TextButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.wallet_outlined, size: 18),
              label: const Text('Финансы'),
              style: TextButton.styleFrom(
                backgroundColor: const Color(0xFFF1EFFF),
                foregroundColor: const Color(0xFF5546F7),
              ),
            ),
            if (onOpenAdmin != null) ...[
              const SizedBox(width: 4),
              TextButton.icon(
                onPressed: onOpenAdmin,
                icon: const Icon(Icons.admin_panel_settings_outlined, size: 18),
                label: const Text('Админ'),
              ),
            ],
          ],
        );
        final selector = users.isEmpty || selectedUserId == null
            ? const SizedBox.shrink()
            : SizedBox(
                width: math.min(220.0, c.maxWidth),
                child: DropdownButtonFormField<String>(
                  key: ValueKey<String?>(selectedUserId),
                  initialValue: selectedUserId,
                  isDense: true,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.person_outline),
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 11,
                    ),
                  ),
                  items: users
                      .map(
                        (u) => DropdownMenuItem(
                          value: u.id,
                          child: Text(
                            u.label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (v) {
                    if (v != null) onUserSelected?.call(v);
                  },
                ),
              );
        final add = FilledButton.icon(
          onPressed: onAddExpense,
          icon: const Icon(Icons.add, size: 19),
          label: const Text('Добавить расход'),
          style: FilledButton.styleFrom(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(13),
            ),
          ),
        );
        if (narrow) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [logo, add],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [nav, if (users.isNotEmpty) selector],
              ),
            ],
          );
        }
        return Row(
          children: [
            logo,
            const SizedBox(width: 22),
            nav,
            const Spacer(),
            selector,
            if (users.isNotEmpty) const SizedBox(width: 10),
            add,
          ],
        );
      },
    ),
  );
}

class _EmptyFinance extends StatelessWidget {
  const _EmptyFinance({required this.onCreateAccount});
  final VoidCallback onCreateAccount;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(44),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(22),
      border: Border.all(color: const Color(0xFFE8EBF2)),
    ),
    child: Column(
      children: [
        Container(
          width: 76,
          height: 76,
          decoration: const BoxDecoration(
            color: Color(0xFFF0EEFF),
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.account_balance_wallet_outlined,
            size: 36,
            color: Color(0xFF5546F7),
          ),
        ),
        const SizedBox(height: 18),
        const Text(
          'Начните с первого счёта',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        const Text(
          'Добавьте карту, наличные или накопительный счёт. Smart Planner объединит их в общий баланс и построит аналитику.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Color(0xFF74798C)),
        ),
        const SizedBox(height: 20),
        FilledButton.icon(
          onPressed: onCreateAccount,
          icon: const Icon(Icons.add),
          label: const Text('Добавить счёт'),
        ),
      ],
    ),
  );
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.data, required this.onAddAccount});
  final FinanceSnapshot data;
  final VoidCallback onAddAccount;
  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: _PanelTitle(
                title: 'Общий баланс',
                subtitle: 'Все ваши счета в рублях',
              ),
            ),
            OutlinedButton.icon(
              onPressed: onAddAccount,
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Счёт'),
            ),
          ],
        ),
        const SizedBox(height: 20),
        Wrap(
          spacing: 26,
          runSpacing: 20,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 210,
              height: 210,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  CustomPaint(
                    size: const Size.square(210),
                    painter: _AccountDonutPainter(data.accounts),
                  ),
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        'Всего',
                        style: TextStyle(color: Color(0xFF8B90A1)),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        formatRubles(data.totalBalanceCents),
                        style: const TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w900,
                          letterSpacing: -0.7,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            SizedBox(
              width: 360,
              child: Column(
                children: data.accounts.map((a) {
                  final int positiveTotal = data.accounts.fold<int>(
                    0,
                    (sum, item) =>
                        sum + (item.balanceCents > 0 ? item.balanceCents : 0),
                  );
                  final double share = positiveTotal == 0
                      ? 0
                      : (a.balanceCents > 0 ? a.balanceCents : 0) /
                            positiveTotal;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 7),
                    child: Row(
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: a.account.color,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                a.account.name,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              Text(
                                '${(share * 100).clamp(0, 999).toStringAsFixed(0)}% баланса',
                                style: const TextStyle(
                                  color: Color(0xFF9297A8),
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Text(
                          formatRubles(a.balanceCents),
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}

class _ExpenseSummary extends StatelessWidget {
  const _ExpenseSummary({required this.data});
  final FinanceSnapshot data;
  @override
  Widget build(BuildContext context) {
    final prev = data.previousMonthExpenseCents;
    final diff = prev == 0
        ? null
        : (data.monthExpenseCents - prev) / prev * 100;
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PanelTitle(
            title: 'Расходы месяца',
            subtitle: 'Фактические списания, без переводов',
          ),
          const SizedBox(height: 24),
          Text(
            formatRubles(data.monthExpenseCents),
            style: const TextStyle(
              fontSize: 34,
              fontWeight: FontWeight.w900,
              letterSpacing: -1,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Icon(
                diff != null && diff <= 0
                    ? Icons.trending_down
                    : Icons.trending_up,
                size: 18,
                color: diff != null && diff <= 0
                    ? const Color(0xFF21A66D)
                    : const Color(0xFFE16954),
              ),
              const SizedBox(width: 6),
              Text(
                diff == null
                    ? 'Пока нет данных прошлого месяца'
                    : '${diff.abs().toStringAsFixed(0)}% к прошлому месяцу',
                style: const TextStyle(color: Color(0xFF74798C)),
              ),
            ],
          ),
          const SizedBox(height: 28),
          Row(
            children: [
              Expanded(
                child: _MiniMetric(
                  label: 'Сегодня',
                  value: formatRubles(data.todayExpenseCents),
                  icon: Icons.today_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _MiniMetric(
                  label: 'В среднем / день',
                  value: formatRubles(data.averageDailyExpenseCents),
                  icon: Icons.speed_outlined,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SpendingTrendCard extends StatelessWidget {
  const _SpendingTrendCard({required this.data});
  final FinanceSnapshot data;
  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _PanelTitle(
          title: 'Динамика расходов',
          subtitle: 'По дням текущего месяца',
        ),
        const SizedBox(height: 18),
        SizedBox(
          height: 220,
          child: CustomPaint(
            painter: _SpendingLinePainter(data.dailySpend),
            child: const SizedBox.expand(),
          ),
        ),
      ],
    ),
  );
}

class _CategoriesCard extends StatelessWidget {
  const _CategoriesCard({required this.data, required this.onAdd});
  final FinanceSnapshot data;
  final VoidCallback onAdd;
  @override
  Widget build(BuildContext context) {
    final total = math.max(1, data.monthExpenseCents);
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: _PanelTitle(
                  title: 'Куда уходят деньги',
                  subtitle: 'Категории текущего месяца',
                ),
              ),
              IconButton(
                onPressed: onAdd,
                tooltip: 'Новая категория',
                icon: const Icon(Icons.add_circle_outline),
              ),
            ],
          ),
          const SizedBox(height: 18),
          if (data.categorySpend.isEmpty)
            const _EmptyLine(text: 'Расходов пока нет')
          else
            ...data.categorySpend.take(6).map((c) {
              final p = c.amountCents / total;
              return Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: c.color,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            c.name,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                        Text(
                          formatRubles(c.amountCents),
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: LinearProgressIndicator(
                        value: p,
                        color: c.color,
                        backgroundColor: const Color(0xFFF0F1F6),
                        minHeight: 7,
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.viewModel});
  final FinanceViewModel viewModel;
  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 10,
    runSpacing: 10,
    children: [
      _ActionButton(
        icon: Icons.south_east,
        label: 'Расход',
        onTap: () => showAddTransactionDialog(context, viewModel),
      ),
      _ActionButton(
        icon: Icons.north_east,
        label: 'Доход',
        onTap: () => showAddTransactionDialog(
          context,
          viewModel,
          initialType: FinanceTransactionType.income,
        ),
      ),
      _ActionButton(
        icon: Icons.swap_horiz,
        label: 'Перевод',
        onTap: () => showAddTransactionDialog(
          context,
          viewModel,
          initialType: FinanceTransactionType.transfer,
        ),
      ),
      _ActionButton(
        icon: Icons.savings_outlined,
        label: 'Финансовая цель',
        onTap: () => showAddFinancialGoalDialog(context, viewModel),
      ),
      _ActionButton(
        icon: Icons.event_repeat_outlined,
        label: 'Платёж',
        onTap: () => showAddPaymentDialog(context, viewModel),
      ),
      _ActionButton(
        icon: Icons.handshake_outlined,
        label: 'Долг',
        onTap: () => showAddDebtDialog(context, viewModel),
      ),
    ],
  );
}

class _GoalsCard extends StatelessWidget {
  const _GoalsCard({
    required this.data,
    required this.viewModel,
    required this.onAdd,
  });

  final FinanceSnapshot data;
  final FinanceViewModel viewModel;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: _PanelTitle(
                title: 'Финансовые цели',
                subtitle: 'Накопления и прогресс',
              ),
            ),
            IconButton(
              onPressed: onAdd,
              tooltip: 'Новая финансовая цель',
              icon: const Icon(Icons.add_circle_outline),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (data.goals.isEmpty)
          const _EmptyLine(text: 'Добавьте первую цель')
        else
          ...data.goals
              .take(4)
              .map(
                (goal) => Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              goal.title,
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          Text(
                            '${(goal.progress * 100).toStringAsFixed(0)}%',
                            style: const TextStyle(
                              color: Color(0xFF5546F7),
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 7),
                      LinearProgressIndicator(
                        value: goal.progress,
                        minHeight: 8,
                        borderRadius: BorderRadius.circular(8),
                        backgroundColor: const Color(0xFFF0F1F6),
                      ),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${formatRubles(goal.savedCents)} из ${formatRubles(goal.targetCents)}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFF8B90A1),
                              ),
                            ),
                          ),
                          if (goal.linkedAccountId == null)
                            TextButton(
                              onPressed: () => showAddGoalSavingsDialog(
                                context,
                                viewModel,
                                goal,
                              ),
                              child: const Text('Пополнить'),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
      ],
    ),
  );
}

class _PaymentsCard extends StatelessWidget {
  const _PaymentsCard({
    required this.data,
    required this.viewModel,
    required this.onAdd,
  });

  final FinanceSnapshot data;
  final FinanceViewModel viewModel;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: _PanelTitle(
                title: 'Ближайшие платежи',
                subtitle: 'С напоминаниями в календаре',
              ),
            ),
            IconButton(
              onPressed: onAdd,
              tooltip: 'Новый обязательный платёж',
              icon: const Icon(Icons.add_circle_outline),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (data.payments.isEmpty)
          const _EmptyLine(text: 'Нет обязательных платежей')
        else
          ...data.payments
              .take(5)
              .map(
                (payment) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF4E5),
                      borderRadius: BorderRadius.circular(11),
                    ),
                    child: const Icon(
                      Icons.receipt_long_outlined,
                      color: Color(0xFFE59224),
                      size: 20,
                    ),
                  ),
                  title: Text(
                    payment.title,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  subtitle: Text(
                    '${payment.dueDate.day}.${payment.dueDate.month}.${payment.dueDate.year}'
                    '${payment.recurrence == FinanceRecurrence.monthly ? ' · ежемесячно' : ''}',
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        formatRubles(payment.amountCents),
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(width: 6),
                      TextButton(
                        onPressed: () => _confirmPayment(context, payment),
                        child: const Text('Оплачено'),
                      ),
                    ],
                  ),
                ),
              ),
      ],
    ),
  );
  Future<void> _confirmPayment(
    BuildContext context,
    FinancePayment payment,
  ) async {
    final bool confirmed =
        await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Подтвердить оплату'),
            content: Text(
              'Записать расход «${payment.title}» на сумму ${formatRubles(payment.amountCents)}?',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Отмена'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('Подтвердить'),
              ),
            ],
          ),
        ) ??
        false;
    if (confirmed) await viewModel.payPayment(payment);
  }
}

class _DebtsCard extends StatelessWidget {
  const _DebtsCard({
    required this.data,
    required this.viewModel,
    required this.onAdd,
  });

  final FinanceSnapshot data;
  final FinanceViewModel viewModel;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: _PanelTitle(
                title: 'Долги',
                subtitle: 'Отдельно от реального баланса',
              ),
            ),
            IconButton(
              onPressed: onAdd,
              tooltip: 'Добавить долг',
              icon: const Icon(Icons.add_circle_outline),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (data.debts.isEmpty)
          const _EmptyLine(text: 'Открытых долгов нет')
        else
          ...data.debts
              .take(5)
              .map(
                (debt) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    debt.direction == FinanceDebtDirection.owedToMe
                        ? Icons.call_received
                        : Icons.call_made,
                    color: debt.direction == FinanceDebtDirection.owedToMe
                        ? const Color(0xFF21A66D)
                        : const Color(0xFFE16954),
                  ),
                  title: Text(
                    debt.title,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  subtitle: Text(
                    '${debt.direction == FinanceDebtDirection.owedToMe ? 'Мне должны' : 'Я должен'}'
                    '${debt.person.isEmpty ? '' : ' · ${debt.person}'}',
                  ),
                  trailing: PopupMenuButton<String>(
                    onSelected: (value) {
                      if (value == 'settle') viewModel.settleDebt(debt);
                    },
                    itemBuilder: (_) => [
                      PopupMenuItem(
                        value: 'settle',
                        child: Text(
                          'Закрыть · ${formatRubles(debt.amountCents)}',
                        ),
                      ),
                    ],
                    child: Text(
                      formatRubles(debt.amountCents),
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                  ),
                ),
              ),
      ],
    ),
  );
}

class _RecentTransactions extends StatelessWidget {
  const _RecentTransactions({required this.data, required this.viewModel});

  final FinanceSnapshot data;
  final FinanceViewModel viewModel;

  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _PanelTitle(
          title: 'Последние операции',
          subtitle: 'Фактическое движение денег',
        ),
        const SizedBox(height: 10),
        if (data.recentTransactions.isEmpty)
          const _EmptyLine(text: 'Операций пока нет')
        else
          ...data.recentTransactions.map((transaction) {
            final account =
                data.accounts
                    .where((item) => item.account.id == transaction.accountId)
                    .map((item) => item.account.name)
                    .firstOrNull ??
                'Счёт';
            final category = data.categories
                .where((item) => item.id == transaction.categoryId)
                .map((item) => item.name)
                .firstOrNull;
            final positive = transaction.type == FinanceTransactionType.income;
            final prefix = transaction.type == FinanceTransactionType.transfer
                ? '↔ '
                : positive
                ? '+ '
                : '− ';
            return ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color:
                      (positive
                              ? const Color(0xFF21A66D)
                              : const Color(0xFF5546F7))
                          .withValues(alpha: .09),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  transaction.type == FinanceTransactionType.transfer
                      ? Icons.swap_horiz
                      : positive
                      ? Icons.north_east
                      : Icons.south_east,
                  color: positive
                      ? const Color(0xFF21A66D)
                      : const Color(0xFF5546F7),
                ),
              ),
              title: Text(
                transaction.note.isEmpty
                    ? (category ??
                          (transaction.type == FinanceTransactionType.transfer
                              ? 'Перевод'
                              : 'Операция'))
                    : transaction.note,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Text(
                '$account · ${transaction.occurredAt.day}.${transaction.occurredAt.month}.${transaction.occurredAt.year}',
              ),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '$prefix${formatRubles(transaction.amountCents)}',
                    style: TextStyle(
                      fontWeight: FontWeight.w900,
                      color: positive
                          ? const Color(0xFF21A66D)
                          : const Color(0xFF252A3B),
                    ),
                  ),
                  PopupMenuButton<String>(
                    onSelected: (value) {
                      if (value == 'delete') {
                        viewModel.deleteTransaction(transaction.id);
                      }
                    },
                    itemBuilder: (_) => const [
                      PopupMenuItem(
                        value: 'delete',
                        child: Text('Удалить операцию'),
                      ),
                    ],
                  ),
                ],
              ),
            );
          }),
      ],
    ),
  );
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: const Color(0xFFE8EBF2)),
      boxShadow: const [
        BoxShadow(
          color: Color(0x0825315A),
          blurRadius: 18,
          offset: Offset(0, 4),
        ),
      ],
    ),
    child: child,
  );
}

class _PanelTitle extends StatelessWidget {
  const _PanelTitle({required this.title, required this.subtitle});
  final String title, subtitle;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        title,
        style: const TextStyle(
          fontSize: 17,
          fontWeight: FontWeight.w900,
          letterSpacing: -.3,
        ),
      ),
      const SizedBox(height: 3),
      Text(
        subtitle,
        style: const TextStyle(fontSize: 12, color: Color(0xFF8C91A3)),
      ),
    ],
  );
}

class _MiniMetric extends StatelessWidget {
  const _MiniMetric({
    required this.label,
    required this.value,
    required this.icon,
  });
  final String label, value;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: const Color(0xFFF8F8FD),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 19, color: const Color(0xFF5546F7)),
        const SizedBox(height: 10),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w900)),
        const SizedBox(height: 2),
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: Color(0xFF8B90A1)),
        ),
      ],
    ),
  );
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    onPressed: onTap,
    icon: Icon(icon, size: 18),
    label: Text(label),
    style: OutlinedButton.styleFrom(
      backgroundColor: Colors.white,
      foregroundColor: const Color(0xFF30364A),
      side: const BorderSide(color: Color(0xFFE4E6EF)),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
    ),
  );
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.text});
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 20),
    child: Center(
      child: Text(text, style: const TextStyle(color: Color(0xFF999EAF))),
    ),
  );
}

class _AccountDonutPainter extends CustomPainter {
  const _AccountDonutPainter(this.accounts);

  final List<FinanceAccountBalance> accounts;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2 - 16;
    const stroke = 22.0;
    final total = accounts.fold<int>(
      0,
      (sum, account) =>
          sum + (account.balanceCents > 0 ? account.balanceCents : 0),
    );
    final base = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..color = const Color(0xFFF0F1F6);
    canvas.drawCircle(center, radius, base);
    if (total <= 0) {
      return;
    }

    var start = -math.pi / 2;
    for (final account in accounts) {
      final value = account.balanceCents > 0 ? account.balanceCents : 0;
      if (value == 0) {
        continue;
      }
      final sweep = value / total * math.pi * 2;
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..strokeCap = StrokeCap.butt
        ..color = account.account.color;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        start,
        sweep,
        false,
        paint,
      );
      start += sweep;
    }
  }

  @override
  bool shouldRepaint(covariant _AccountDonutPainter oldDelegate) =>
      oldDelegate.accounts != accounts;
}

class _SpendingLinePainter extends CustomPainter {
  const _SpendingLinePainter(this.points);

  final List<FinanceDailySpend> points;

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = const Color(0xFFEDEFF5)
      ..strokeWidth = 1;
    for (var i = 0; i < 5; i++) {
      final y = 16 + (size.height - 34) * i / 4;
      canvas.drawLine(Offset(8, y), Offset(size.width - 8, y), grid);
    }
    if (points.isEmpty) {
      return;
    }

    final maxValue = points
        .map((point) => point.amountCents)
        .fold<int>(1, (a, b) => a > b ? a : b);
    final path = Path();
    for (var i = 0; i < points.length; i++) {
      final x =
          12 +
          (size.width - 24) *
              (points.length == 1 ? 0.5 : i / (points.length - 1));
      final y =
          size.height -
          18 -
          (size.height - 42) * (points[i].amountCents / maxValue);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }

    final shadow = Paint()
      ..color = const Color(0x225546F7)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(path, shadow);

    final line = Paint()
      ..color = const Color(0xFF5546F7)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(path, line);
  }

  @override
  bool shouldRepaint(covariant _SpendingLinePainter oldDelegate) =>
      oldDelegate.points != points;
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
