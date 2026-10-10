import 'package:flutter/material.dart';

import '../../planner/domain/planner_user.dart';
import '../application/admin_subscription_view_model.dart';
import '../domain/subscription_models.dart';

class AdminSubscriptionPage extends StatefulWidget {
  const AdminSubscriptionPage({
    required this.viewModel,
    required this.users,
    required this.onOpenPlanner,
    required this.onOpenFinance,
    this.onUserSelected,
    this.initialUserId,
    super.key,
  });

  final AdminSubscriptionViewModel viewModel;
  final List<PlannerUser> users;
  final String? initialUserId;
  final VoidCallback onOpenPlanner;
  final VoidCallback? onOpenFinance;
  final ValueChanged<String>? onUserSelected;

  @override
  State<AdminSubscriptionPage> createState() => _AdminSubscriptionPageState();
}

class _AdminSubscriptionPageState extends State<AdminSubscriptionPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureSelected());
  }

  @override
  void didUpdateWidget(covariant AdminSubscriptionPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialUserId != widget.initialUserId ||
        oldWidget.users != widget.users) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _ensureSelected());
    }
  }

  void _ensureSelected() {
    if (!mounted || widget.viewModel.saving) {
      return;
    }
    final candidates = widget.users
        .where((user) => user.role != 'admin')
        .toList();
    if (candidates.isEmpty) {
      return;
    }
    final requested = widget.initialUserId;
    final selected = candidates.any((user) => user.id == requested)
        ? requested!
        : candidates.first.id;
    if (widget.viewModel.selectedUserId != selected ||
        widget.viewModel.snapshot == null) {
      widget.viewModel.selectUser(selected);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.viewModel,
      builder: (context, _) {
        return Scaffold(
          body: SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final compact = constraints.maxWidth < 900;
                return SingleChildScrollView(
                  padding: EdgeInsets.all(compact ? 12 : 18),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 1500),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _AdminHeader(
                            users: widget.users,
                            selectedUserId: widget.viewModel.selectedUserId,
                            onSelected: _selectUser,
                            onOpenPlanner: widget.onOpenPlanner,
                            onOpenFinance: widget.onOpenFinance,
                          ),
                          const SizedBox(height: 16),
                          _buildBody(context, compact),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  void _selectUser(String userId) {
    widget.viewModel.selectUser(userId);
    PlannerUser? selectedUser;
    for (final PlannerUser user in widget.users) {
      if (user.id == userId) {
        selectedUser = user;
        break;
      }
    }
    if (selectedUser?.status == 'active') {
      widget.onUserSelected?.call(userId);
    }
  }

  Widget _buildBody(BuildContext context, bool compact) {
    final vm = widget.viewModel;
    if (widget.users.where((user) => user.role != 'admin').isEmpty) {
      return const _Panel(
        child: Padding(
          padding: EdgeInsets.all(30),
          child: Text('Пользователей пока нет.'),
        ),
      );
    }
    if (vm.loadState == AdminSubscriptionLoadState.loading ||
        vm.snapshot == null) {
      return const Padding(
        padding: EdgeInsets.all(60),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (vm.loadState == AdminSubscriptionLoadState.error) {
      return _Panel(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              Text(vm.errorMessage ?? 'Не удалось загрузить подписку'),
              const SizedBox(height: 14),
              FilledButton(
                onPressed: vm.selectedUserId == null
                    ? null
                    : () => vm.selectUser(vm.selectedUserId!),
                child: const Text('Повторить'),
              ),
            ],
          ),
        ),
      );
    }

    final snapshot = vm.snapshot!;
    final user = widget.users.firstWhere(
      (item) => item.id == snapshot.userId,
      orElse: () => widget.users.first,
    );
    final overview = _SubscriptionOverview(
      user: user,
      snapshot: snapshot,
      saving: vm.saving,
      onChangePlan: () => _showPlanDialog(context),
      onTrial: () => _showTrialDialog(context),
      onExtra: () => _showExtraDialog(context),
      onReset: () => _confirmReset(context),
    );
    final usage = _UsagePanel(snapshot: snapshot, user: user);
    final overrides = _OverridesPanel(
      overrides: snapshot.overrides,
      saving: vm.saving,
      onDelete: vm.removeOverride,
    );
    final audit = _AuditPanel(records: vm.audit);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xFFFFF7E8),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFF0D7A4)),
          ),
          child: const Row(
            children: [
              Icon(
                Icons.visibility_outlined,
                size: 20,
                color: Color(0xFF9B6500),
              ),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Режим администратора: календарь и финансы пользователя доступны только для просмотра. Здесь меняются только подписка, trial и временные допы.',
                  style: TextStyle(
                    color: Color(0xFF72500D),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        if (compact) ...[
          overview,
          const SizedBox(height: 14),
          usage,
        ] else
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 7, child: overview),
              const SizedBox(width: 14),
              Expanded(flex: 5, child: usage),
            ],
          ),
        const SizedBox(height: 14),
        overrides,
        const SizedBox(height: 14),
        audit,
        if (vm.errorMessage != null) ...[
          const SizedBox(height: 12),
          Text(vm.errorMessage!, style: const TextStyle(color: Colors.red)),
        ],
      ],
    );
  }

  Future<void> _showPlanDialog(BuildContext context) async {
    final vm = widget.viewModel;
    final current = vm.snapshot!;
    String plan = current.plan;
    String billing = current.billingPeriod == 'trial'
        ? 'manual'
        : current.billingPeriod;
    DateTime? expiresAt = current.expiresAt;
    final result = await showDialog<_PlanDraft>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Изменить подписку'),
          content: SizedBox(
            width: 440,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: plan,
                  decoration: const InputDecoration(labelText: 'Тариф'),
                  items: const [
                    DropdownMenuItem(value: 'free', child: Text('Free')),
                    DropdownMenuItem(value: 'plus', child: Text('Plus')),
                    DropdownMenuItem(value: 'full', child: Text('Full')),
                  ],
                  onChanged: (value) => setState(() => plan = value ?? plan),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: billing,
                  decoration: const InputDecoration(labelText: 'Период'),
                  items: const [
                    DropdownMenuItem(
                      value: 'manual',
                      child: Text('Ручная выдача'),
                    ),
                    DropdownMenuItem(value: 'monthly', child: Text('Месяц')),
                    DropdownMenuItem(value: 'yearly', child: Text('Год')),
                  ],
                  onChanged: (value) =>
                      setState(() => billing = value ?? billing),
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Дата окончания'),
                  subtitle: Text(
                    expiresAt == null
                        ? 'Без срока'
                        : '${expiresAt!.day.toString().padLeft(2, '0')}.${expiresAt!.month.toString().padLeft(2, '0')}.${expiresAt!.year}',
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (expiresAt != null)
                        IconButton(
                          tooltip: 'Без срока',
                          onPressed: () => setState(() => expiresAt = null),
                          icon: const Icon(Icons.clear),
                        ),
                      IconButton(
                        tooltip: 'Выбрать дату',
                        onPressed: () async {
                          final date = await showDatePicker(
                            context: dialogContext,
                            initialDate:
                                expiresAt ??
                                DateTime.now().add(const Duration(days: 30)),
                            firstDate: DateTime.now(),
                            lastDate: DateTime.now().add(
                              const Duration(days: 3650),
                            ),
                          );
                          if (date != null) {
                            setState(() => expiresAt = date);
                          }
                        },
                        icon: const Icon(Icons.event_outlined),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(
                dialogContext,
                _PlanDraft(plan, billing, expiresAt),
              ),
              child: const Text('Сохранить'),
            ),
          ],
        ),
      ),
    );
    if (result != null && mounted) {
      await vm.changePlan(
        plan: result.plan,
        billingPeriod: result.billing,
        expiresAt: result.expiresAt,
      );
    }
  }

  Future<void> _showTrialDialog(BuildContext context) async {
    final controller = TextEditingController(text: '14');
    final days = await showDialog<int>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Выдать Full Trial'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Количество дней',
            suffixText: 'дн.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () {
              final value = int.tryParse(controller.text.trim());
              Navigator.pop(
                dialogContext,
                value != null && value > 0 ? value : null,
              );
            },
            child: const Text('Выдать'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (days != null && mounted) {
      await widget.viewModel.grantTrial(days.clamp(1, 365).toInt());
    }
  }

  Future<void> _showExtraDialog(BuildContext context) async {
    String kind = 'entitlement';
    String key = 'finance';
    int amount = 100;
    int days = 30;
    final reasonController = TextEditingController();
    final draft = await showDialog<_ExtraDraft>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Выдать временный доп'),
          content: SizedBox(
            width: 460,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'entitlement', label: Text('Доступ')),
                    ButtonSegment(
                      value: 'limit_bonus',
                      label: Text('Бонус лимита'),
                    ),
                  ],
                  selected: <String>{kind},
                  onSelectionChanged: (value) {
                    setState(() {
                      kind = value.first;
                      key = kind == 'entitlement'
                          ? 'finance'
                          : 'ai_actions_monthly';
                    });
                  },
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  key: ValueKey('$kind-$key'),
                  initialValue: key,
                  decoration: const InputDecoration(labelText: 'Возможность'),
                  items:
                      (kind == 'entitlement'
                              ? const <MapEntry<String, String>>[
                                  MapEntry('finance', 'Финансы'),
                                  MapEntry(
                                    'finance_telegram',
                                    'Финансы в Telegram',
                                  ),
                                  MapEntry(
                                    'smart_scheduling',
                                    'Умное планирование',
                                  ),
                                  MapEntry(
                                    'multi_task_recognition',
                                    'Несколько задач в сообщении',
                                  ),
                                  MapEntry(
                                    'advanced_reports',
                                    'Расширенные отчёты',
                                  ),
                                ]
                              : const <MapEntry<String, String>>[
                                  MapEntry('ai_actions_monthly', 'AI-действия'),
                                  MapEntry(
                                    'voice_messages_monthly',
                                    'Голосовые сообщения',
                                  ),
                                  MapEntry('groups', 'Группы'),
                                  MapEntry('goals', 'Цели'),
                                ])
                          .map(
                            (entry) => DropdownMenuItem(
                              value: entry.key,
                              child: Text(entry.value),
                            ),
                          )
                          .toList(),
                  onChanged: (value) => setState(() => key = value ?? key),
                ),
                if (kind == 'limit_bonus') ...[
                  const SizedBox(height: 12),
                  TextFormField(
                    initialValue: amount.toString(),
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Добавить к лимиту',
                    ),
                    onChanged: (value) =>
                        amount = int.tryParse(value) ?? amount,
                  ),
                ],
                const SizedBox(height: 12),
                TextFormField(
                  initialValue: days.toString(),
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Срок действия',
                    suffixText: 'дн.',
                  ),
                  onChanged: (value) => days = int.tryParse(value) ?? days,
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: reasonController,
                  decoration: const InputDecoration(
                    labelText: 'Причина / комментарий',
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(
                dialogContext,
                _ExtraDraft(
                  kind,
                  key,
                  amount,
                  days,
                  reasonController.text.trim(),
                ),
              ),
              child: const Text('Выдать'),
            ),
          ],
        ),
      ),
    );
    reasonController.dispose();
    if (draft == null || !mounted) {
      return;
    }
    final expires = DateTime.now().add(
      Duration(days: draft.days.clamp(1, 3650).toInt()),
    );
    if (draft.kind == 'entitlement') {
      await widget.viewModel.grantEntitlement(
        key: draft.key,
        value: true,
        expiresAt: expires,
        reason: draft.reason,
      );
    } else {
      await widget.viewModel.grantLimitBonus(
        key: draft.key,
        amount: draft.amount.clamp(1, 1000000).toInt(),
        expiresAt: expires,
        reason: draft.reason,
      );
    }
  }

  Future<void> _confirmReset(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Сбросить подписку на Free?'),
        content: const Text(
          'Платный доступ завершится, но данные не удалятся. Финансы останутся доступны только для чтения.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Сбросить'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await widget.viewModel.resetToFree();
    }
  }
}

class _AdminHeader extends StatelessWidget {
  const _AdminHeader({
    required this.users,
    required this.selectedUserId,
    required this.onSelected,
    required this.onOpenPlanner,
    required this.onOpenFinance,
  });
  final List<PlannerUser> users;
  final String? selectedUserId;
  final ValueChanged<String> onSelected;
  final VoidCallback onOpenPlanner;
  final VoidCallback? onOpenFinance;

  @override
  Widget build(BuildContext context) {
    final selectable = users.where((user) => user.role != 'admin').toList();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE8EBF2)),
      ),
      child: Wrap(
        spacing: 10,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.admin_panel_settings_outlined,
                color: Color(0xFF5546F7),
              ),
              SizedBox(width: 9),
              Text(
                'Администрирование',
                style: TextStyle(fontWeight: FontWeight.w900, fontSize: 17),
              ),
            ],
          ),
          TextButton.icon(
            onPressed: onOpenPlanner,
            icon: const Icon(Icons.calendar_today_outlined),
            label: const Text('Календарь'),
          ),
          if (onOpenFinance != null)
            TextButton.icon(
              onPressed: onOpenFinance,
              icon: const Icon(Icons.wallet_outlined),
              label: const Text('Финансы'),
            ),
          if (selectable.isNotEmpty)
            SizedBox(
              width: 300,
              child: DropdownButtonFormField<String>(
                key: ValueKey(selectedUserId),
                initialValue:
                    selectable.any((user) => user.id == selectedUserId)
                    ? selectedUserId
                    : selectable.first.id,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Пользователь'),
                items: selectable
                    .map(
                      (user) => DropdownMenuItem(
                        value: user.id,
                        child: Text(
                          user.label,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    )
                    .toList(),
                onChanged: (value) {
                  if (value != null) {
                    onSelected(value);
                  }
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _SubscriptionOverview extends StatelessWidget {
  const _SubscriptionOverview({
    required this.user,
    required this.snapshot,
    required this.saving,
    required this.onChangePlan,
    required this.onTrial,
    required this.onExtra,
    required this.onReset,
  });
  final PlannerUser user;
  final SubscriptionSnapshot snapshot;
  final bool saving;
  final VoidCallback onChangePlan;
  final VoidCallback onTrial;
  final VoidCallback onExtra;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    final end = snapshot.trialEndsAt ?? snapshot.expiresAt;
    final remaining = end == null
        ? null
        : end.difference(DateTime.now()).inDays + 1;
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 24,
                backgroundColor: const Color(0xFFF0EEFF),
                child: Text(
                  user.displayName.isEmpty
                      ? '?'
                      : user.displayName.substring(0, 1).toUpperCase(),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user.displayName,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    Text(
                      user.username == null
                          ? 'Telegram ID ${user.id}'
                          : '@${user.username}',
                      style: const TextStyle(color: Color(0xFF858A9D)),
                    ),
                  ],
                ),
              ),
              _PlanBadge(plan: snapshot.planLabel),
            ],
          ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _InfoTile(
                label: 'Роль',
                value: user.role == 'admin' ? 'Admin' : 'User',
              ),
              _InfoTile(label: 'Аккаунт', value: user.status),
              _InfoTile(label: 'Подписка', value: snapshot.status),
              _InfoTile(label: 'Период', value: snapshot.billingPeriod),
              _InfoTile(
                label: 'Окончание',
                value: end == null ? 'Без срока' : _dateText(end),
              ),
              if (snapshot.status == 'trial')
                _InfoTile(
                  label: 'Trial',
                  value: '${remaining?.clamp(0, 999) ?? 0} дн.',
                ),
            ],
          ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton.icon(
                onPressed: saving ? null : onChangePlan,
                icon: const Icon(Icons.workspace_premium_outlined),
                label: const Text('Изменить тариф'),
              ),
              OutlinedButton.icon(
                onPressed: saving ? null : onTrial,
                icon: const Icon(Icons.timer_outlined),
                label: const Text('Выдать trial'),
              ),
              OutlinedButton.icon(
                onPressed: saving ? null : onExtra,
                icon: const Icon(Icons.card_giftcard_outlined),
                label: const Text('Выдать доп'),
              ),
              TextButton.icon(
                onPressed: saving ? null : onReset,
                icon: const Icon(Icons.restart_alt),
                label: const Text('Сбросить на Free'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _UsagePanel extends StatelessWidget {
  const _UsagePanel({required this.snapshot, required this.user});
  final SubscriptionSnapshot snapshot;
  final PlannerUser user;
  @override
  Widget build(BuildContext context) {
    const keys = <MapEntry<String, String>>[
      MapEntry('ai_actions_monthly', 'AI-действия'),
      MapEntry('voice_messages_monthly', 'Голос'),
      MapEntry('groups', 'Группы'),
      MapEntry('goals', 'Цели'),
      MapEntry('finance_accounts', 'Финансовые счета'),
    ];
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Лимиты и использование',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 16),
          ...keys.map((entry) {
            final limit = snapshot.limitOf(entry.key);
            final int? used = switch (entry.key) {
              'groups' => user.groupCount,
              'goals' => user.goalCount,
              'finance_accounts' => null,
              _ => snapshot.usageOf(entry.key),
            };
            final unlimited =
                snapshot.isPublicUnlimited(entry.key) || limit < 0;
            final String value;
            if (used == null) {
              value = unlimited ? '∞' : 'лимит $limit';
            } else {
              value = unlimited ? '$used / ∞' : '$used / $limit';
            }
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      entry.value,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                  Text(
                    value,
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                ],
              ),
            );
          }),
          const Divider(),
          Row(
            children: [
              const Expanded(child: Text('Финансы')),
              Text(
                snapshot.financeReadOnly ? 'Только чтение' : 'Полный доступ',
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: snapshot.financeReadOnly
                      ? const Color(0xFFB66B00)
                      : const Color(0xFF168248),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _OverridesPanel extends StatelessWidget {
  const _OverridesPanel({
    required this.overrides,
    required this.saving,
    required this.onDelete,
  });
  final List<SubscriptionOverride> overrides;
  final bool saving;
  final ValueChanged<String> onDelete;
  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Временные допы',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 12),
        if (overrides.isEmpty)
          const Text(
            'Активных временных допов нет.',
            style: TextStyle(color: Color(0xFF8A8FA0)),
          )
        else
          ...overrides.map(
            (item) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const CircleAvatar(child: Icon(Icons.bolt_outlined)),
              title: Text(
                item.key.replaceAll('_', ' '),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Text(
                '${item.kind == 'limit_bonus' ? '+${item.intValue}' : 'Доступ включён'} · до ${_dateText(item.expiresAt.toLocal())}${item.reason.isEmpty ? '' : ' · ${item.reason}'}',
              ),
              trailing: IconButton(
                tooltip: 'Отозвать доп',
                onPressed: saving ? null : () => onDelete(item.id),
                icon: const Icon(Icons.close),
              ),
            ),
          ),
      ],
    ),
  );
}

class _AuditPanel extends StatelessWidget {
  const _AuditPanel({required this.records});
  final List<SubscriptionAuditRecord> records;
  @override
  Widget build(BuildContext context) => _Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'История изменений',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 12),
        if (records.isEmpty)
          const Text(
            'Изменений пока нет.',
            style: TextStyle(color: Color(0xFF8A8FA0)),
          )
        else
          ...records
              .take(20)
              .map(
                (record) => ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.history, size: 20),
                  title: Text(
                    record.action,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  subtitle: Text(
                    '${_dateTimeText(record.createdAt.toLocal())} · actor ${record.actorId}',
                  ),
                ),
              ),
      ],
    ),
  );
}

class _PlanBadge extends StatelessWidget {
  const _PlanBadge({required this.plan});
  final String plan;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
    decoration: BoxDecoration(
      color: const Color(0xFFF0EEFF),
      borderRadius: BorderRadius.circular(99),
    ),
    child: Text(
      plan,
      style: const TextStyle(
        color: Color(0xFF5546F7),
        fontWeight: FontWeight.w900,
      ),
    ),
  );
}

class _InfoTile extends StatelessWidget {
  const _InfoTile({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(minWidth: 135),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: const Color(0xFFF8F8FC),
      borderRadius: BorderRadius.circular(13),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: Color(0xFF8A8FA0)),
        ),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
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
    ),
    child: child,
  );
}

final class _PlanDraft {
  const _PlanDraft(this.plan, this.billing, this.expiresAt);
  final String plan;
  final String billing;
  final DateTime? expiresAt;
}

final class _ExtraDraft {
  const _ExtraDraft(this.kind, this.key, this.amount, this.days, this.reason);
  final String kind;
  final String key;
  final int amount;
  final int days;
  final String reason;
}

String _dateText(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}';

String _dateTimeText(DateTime date) =>
    '${_dateText(date)} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
