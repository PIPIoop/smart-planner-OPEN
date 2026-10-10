import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/date/date_formatters.dart';
import '../application/planner_view_model.dart';
import '../domain/planner_goal.dart';
import '../domain/planner_task.dart';
import '../domain/planner_user.dart';
import '../domain/task_filter.dart';
import '../domain/task_group.dart';
import 'dialogs/data_transfer_dialogs.dart';
import 'dialogs/goal_editor_dialog.dart';
import 'dialogs/group_manager_dialog.dart';
import 'dialogs/task_editor_dialog.dart';
import 'widgets/calendar_grid.dart';
import 'widgets/goal_progress_panel.dart';
import 'widgets/habit_streak_panel.dart';
import 'widgets/planner_tutorial.dart';
import 'widgets/task_list_panel.dart';

class PlannerPage extends StatefulWidget {
  const PlannerPage({
    required this.viewModel,
    this.users = const <PlannerUser>[],
    this.selectedUserId,
    this.onUserSelected,
    this.onOpenFinance,
    this.onOpenAdmin,
    this.readOnly = false,
    super.key,
  });

  final PlannerViewModel viewModel;
  final List<PlannerUser> users;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;
  final VoidCallback? onOpenFinance;
  final VoidCallback? onOpenAdmin;
  final bool readOnly;

  @override
  State<PlannerPage> createState() => _PlannerPageState();
}

class _PlannerPageState extends State<PlannerPage> {
  final GlobalKey _navigationKey = GlobalKey();
  final GlobalKey _searchKey = GlobalKey();
  final GlobalKey _calendarKey = GlobalKey();
  final GlobalKey _tasksKey = GlobalKey();
  final GlobalKey _addKey = GlobalKey();
  final GlobalKey _dataKey = GlobalKey();

  int? _tutorialStep;
  bool _goalsExpanded = true;

  PlannerViewModel get viewModel => widget.viewModel;

  List<PlannerTutorialStep> get _tutorialSteps => <PlannerTutorialStep>[
    PlannerTutorialStep(
      title: 'Добро пожаловать',
      description:
          'Переключайте разделы, чтобы видеть все, активные или уже выполненные задачи.',
      icon: Icons.space_dashboard_outlined,
      targetKey: _navigationKey,
    ),
    PlannerTutorialStep(
      title: 'Поиск задач',
      description:
          'Введите часть названия или заметки — календарь и список сразу покажут подходящие задачи.',
      icon: Icons.search,
      targetKey: _searchKey,
    ),
    PlannerTutorialStep(
      title: 'Календарь',
      description:
          'Переключайте месяцы стрелками и нажимайте на день, чтобы открыть его задачи справа.',
      icon: Icons.calendar_month_outlined,
      targetKey: _calendarKey,
    ),
    PlannerTutorialStep(
      title: 'План выбранного дня',
      description:
          'Здесь можно отметить задачу выполненной, отредактировать её или удалить через меню с тремя точками.',
      icon: Icons.checklist_outlined,
      targetKey: _tasksKey,
    ),
    PlannerTutorialStep(
      title: 'Новая задача',
      description:
          'Нажмите плюс, заполните название, дату, время и приоритет — задача появится в календаре.',
      icon: Icons.add,
      targetKey: _addKey,
    ),
    PlannerTutorialStep(
      title: 'Резервная копия',
      description:
          'Меню данных позволяет экспортировать задачи в JSON, импортировать резервную копию или очистить список.',
      icon: Icons.more_horiz,
      targetKey: _dataKey,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: viewModel,
      builder: (BuildContext context, Widget? child) {
        return Scaffold(
          body: Stack(
            children: <Widget>[
              _buildBody(context),
              if (_tutorialStep case final int stepIndex)
                Positioned.fill(
                  child: PlannerTutorialOverlay(
                    step: _tutorialSteps[stepIndex],
                    stepIndex: stepIndex,
                    stepCount: _tutorialSteps.length,
                    onPrevious: stepIndex == 0
                        ? null
                        : () => setState(() => _tutorialStep = stepIndex - 1),
                    onNext: () {
                      if (stepIndex == _tutorialSteps.length - 1) {
                        setState(() => _tutorialStep = null);
                      } else {
                        setState(() => _tutorialStep = stepIndex + 1);
                      }
                    },
                    onClose: () => setState(() => _tutorialStep = null),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildBody(BuildContext context) {
    if (viewModel.loadState == PlannerLoadState.loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (viewModel.loadState == PlannerLoadState.error) {
      return Center(
        child: Container(
          constraints: const BoxConstraints(maxWidth: 440),
          padding: const EdgeInsets.all(30),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(
                Icons.error_outline,
                size: 52,
                color: Color(0xFFFF4545),
              ),
              const SizedBox(height: 16),
              Text(
                viewModel.errorMessage ?? 'Неизвестная ошибка',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: viewModel.initialize,
                child: const Text('Повторить'),
              ),
            ],
          ),
        ),
      );
    }

    return SafeArea(
      child: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final bool compact = constraints.maxWidth < 1080;
          final bool compactHeader = constraints.maxWidth < 900;
          final bool mediumHeader =
              !compactHeader && constraints.maxWidth < 1560;
          final EdgeInsets pagePadding = EdgeInsets.all(compact ? 10 : 14);
          final Widget header = _PlannerHeader(
            navigationKey: _navigationKey,
            searchKey: _searchKey,
            addKey: _addKey,
            dataKey: _dataKey,
            compact: compactHeader,
            medium: mediumHeader,
            viewModel: viewModel,
            users: widget.users,
            selectedUserId: widget.selectedUserId,
            onUserSelected: widget.onUserSelected,
            onStartTutorial: () => setState(() => _tutorialStep = 0),
            onOpenFinance: widget.onOpenFinance,
            onOpenAdmin: widget.onOpenAdmin,
            readOnly: widget.readOnly,
            onCreateTask: () => _createTask(context, viewModel.selectedDate),
            onMenuAction: (_PlannerMenuAction action) {
              unawaited(_handleMenuAction(context, action));
            },
          );

          final Widget headerWithMode = Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              header,
              if (widget.readOnly) ...<Widget>[
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF8E8),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFF1D28A)),
                  ),
                  child: const Row(
                    children: <Widget>[
                      Icon(
                        Icons.visibility_outlined,
                        size: 18,
                        color: Color(0xFF8B6417),
                      ),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Режим администратора: данные пользователя доступны только для просмотра.',
                          style: TextStyle(
                            color: Color(0xFF765615),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          );

          final Widget calendar = _CalendarPanel(
            key: _calendarKey,
            viewModel: viewModel,
            fillAvailableHeight: !compact,
          );
          final Widget tasks = TaskListPanel(
            key: _tasksKey,
            date: viewModel.selectedDate,
            tasks: viewModel.selectedDateTasks,
            groups: viewModel.groups,
            isSaving: viewModel.isSaving,
            fillAvailableHeight: !compact,
            onAdd: () => _createTask(context, viewModel.selectedDate),
            onToggle: (PlannerTask task) {
              if (_blockReadOnly(context)) return;
              unawaited(
                _runAction(
                  context,
                  () => viewModel.toggleTaskCompletion(task.id),
                ),
              );
            },
            onEdit: (PlannerTask task) => _editTask(context, task),
            onDelete: (PlannerTask task) => _deleteTask(context, task),
          );

          final Widget goals = GoalProgressPanel(
            goals: viewModel.goals,
            tasks: viewModel.tasks,
            expanded: _goalsExpanded,
            now: DateTime.now(),
            onToggleExpanded: () =>
                setState(() => _goalsExpanded = !_goalsExpanded),
            onAdd: () => _createGoal(context),
            onDelete: (PlannerGoal goal) => _deleteGoal(context, goal),
          );

          final Widget habits = HabitStreakPanel(
            goals: viewModel.goals,
            tasks: viewModel.tasks,
            referenceDate: viewModel.selectedDate,
            today: DateTime.now(),
          );

          if (compact) {
            return SingleChildScrollView(
              padding: pagePadding,
              child: Column(
                children: <Widget>[
                  headerWithMode,
                  const SizedBox(height: 12),
                  calendar,
                  const SizedBox(height: 12),
                  goals,
                  const SizedBox(height: 12),
                  tasks,
                  const SizedBox(height: 12),
                  habits,
                  const SizedBox(height: 12),
                ],
              ),
            );
          }

          return Padding(
            padding: pagePadding,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1720),
                child: Column(
                  children: <Widget>[
                    headerWithMode,
                    const SizedBox(height: 14),
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          Expanded(flex: 10, child: calendar),
                          const SizedBox(width: 14),
                          SizedBox(
                            width: 390,
                            child: Column(
                              children: <Widget>[
                                goals,
                                const SizedBox(height: 12),
                                Expanded(child: tasks),
                                const SizedBox(height: 12),
                                habits,
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _createGoal(BuildContext context) async {
    if (_blockReadOnly(context)) return;
    final GoalDraft? draft = await showGoalEditorDialog(
      context: context,
      initialDate: viewModel.selectedDate,
    );
    if (draft != null && context.mounted) {
      await _runAction(context, () => viewModel.createGoal(draft));
    }
  }

  Future<void> _deleteGoal(BuildContext context, PlannerGoal goal) async {
    if (_blockReadOnly(context)) return;
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Удалить цель?'),
        content: Text('«${goal.title}» и все связанные задачи будут удалены.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Удалить цель'),
          ),
        ],
      ),
    );
    if ((confirmed ?? false) && context.mounted) {
      await _runAction(context, () => viewModel.deleteGoal(goal.id));
    }
  }

  Future<void> _createTask(BuildContext context, DateTime date) async {
    if (_blockReadOnly(context)) return;
    final TaskDraft? draft = await showTaskEditorDialog(
      context: context,
      initialDate: date,
      groups: viewModel.groups,
    );
    if (draft != null && context.mounted) {
      await _runAction(context, () => viewModel.createTask(draft));
    }
  }

  Future<void> _editTask(BuildContext context, PlannerTask task) async {
    if (_blockReadOnly(context)) return;
    final TaskDraft? draft = await showTaskEditorDialog(
      context: context,
      initialDate: task.date,
      task: task,
      groups: viewModel.groups,
    );
    if (draft != null && context.mounted) {
      await _runAction(context, () => viewModel.updateTask(task.id, draft));
    }
  }

  Future<void> _deleteTask(BuildContext context, PlannerTask task) async {
    if (_blockReadOnly(context)) return;
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Удалить задачу?'),
        content: Text('«${task.title}» будет удалена.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );

    if ((confirmed ?? false) && context.mounted) {
      await _runAction(context, () => viewModel.deleteTask(task.id));
    }
  }

  Future<void> _handleMenuAction(
    BuildContext context,
    _PlannerMenuAction action,
  ) async {
    if (widget.readOnly && action != _PlannerMenuAction.export) {
      _showReadOnlyMessage(context);
      return;
    }
    switch (action) {
      case _PlannerMenuAction.groups:
        await showGroupManagerDialog(context: context, viewModel: viewModel);
      case _PlannerMenuAction.export:
        await showExportDialog(context: context, json: viewModel.exportJson());
      case _PlannerMenuAction.import:
        final ImportPayload? payload = await showImportDialog(context: context);
        if (payload != null && context.mounted) {
          await _runAction(
            context,
            () => viewModel.importJson(payload.json, payload.mode),
          );
        }
      case _PlannerMenuAction.deleteAll:
        final bool confirmed = await showDeleteAllDialog(context: context);
        if (confirmed && context.mounted) {
          await _runAction(context, viewModel.deleteAllTasks);
        }
    }
  }

  bool _blockReadOnly(BuildContext context) {
    if (!widget.readOnly) {
      return false;
    }
    _showReadOnlyMessage(context);
    return true;
  }

  void _showReadOnlyMessage(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Режим администратора: данные пользователя доступны только для просмотра.',
        ),
      ),
    );
  }

  Future<void> _runAction(
    BuildContext context,
    Future<void> Function() action,
  ) async {
    try {
      await action();
    } on Object catch (error, stackTrace) {
      assert(() {
        debugPrint('Planner action failed: $error');
        debugPrintStack(stackTrace: stackTrace);
        return true;
      }());
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Не удалось выполнить действие. Повторите попытку.'),
          ),
        );
      }
    }
  }
}

enum _PlannerMenuAction { groups, export, import, deleteAll }

class _PlannerHeader extends StatelessWidget {
  const _PlannerHeader({
    required this.navigationKey,
    required this.searchKey,
    required this.addKey,
    required this.dataKey,
    required this.compact,
    required this.medium,
    required this.viewModel,
    required this.users,
    required this.selectedUserId,
    required this.onUserSelected,
    required this.onStartTutorial,
    required this.onOpenFinance,
    required this.onOpenAdmin,
    required this.readOnly,
    required this.onCreateTask,
    required this.onMenuAction,
  });

  final GlobalKey navigationKey;
  final GlobalKey searchKey;
  final GlobalKey addKey;
  final GlobalKey dataKey;
  final bool compact;
  final bool medium;
  final PlannerViewModel viewModel;
  final List<PlannerUser> users;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;
  final VoidCallback onStartTutorial;
  final VoidCallback? onOpenFinance;
  final VoidCallback? onOpenAdmin;
  final bool readOnly;
  final VoidCallback onCreateTask;
  final ValueChanged<_PlannerMenuAction> onMenuAction;

  @override
  Widget build(BuildContext context) {
    final Widget logo = Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            color: const Color(0xFFF0EEFF),
            borderRadius: BorderRadius.circular(11),
          ),
          child: const Icon(
            Icons.calendar_month_rounded,
            color: Color(0xFF5546F7),
            size: 24,
          ),
        ),
        const SizedBox(width: 12),
        Flexible(
          child: Text(
            'Smart Planner',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: const Color(0xFF101426),
              fontWeight: FontWeight.w900,
              letterSpacing: -0.4,
            ),
          ),
        ),
      ],
    );

    final Widget navigation = _HeaderNavigation(
      key: navigationKey,
      selected: viewModel.statusFilter,
      onSelected: viewModel.setStatusFilter,
      onOpenFinance: onOpenFinance,
      onOpenAdmin: onOpenAdmin,
    );
    final Widget? userSelector = users.isEmpty || selectedUserId == null
        ? null
        : _UserCalendarSelector(
            users: users,
            selectedUserId: selectedUserId!,
            onSelected: onUserSelected,
          );
    final Widget search = SizedBox(
      key: searchKey,
      width: compact ? double.infinity : 282,
      child: TextField(
        decoration: const InputDecoration(
          hintText: 'Поиск задач…',
          suffixIcon: Icon(Icons.search, color: Color(0xFF20263A)),
          isDense: true,
        ),
        onChanged: viewModel.setSearchQuery,
      ),
    );
    final Widget tutorialButton = OutlinedButton.icon(
      onPressed: onStartTutorial,
      icon: const Icon(Icons.school_outlined, size: 19),
      label: const Text('Обучение'),
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF5546F7),
        side: const BorderSide(color: Color(0xFFDCD8FF)),
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
      ),
    );
    final Widget compactTutorialButton = MediaQuery.sizeOf(context).width >= 440
        ? TextButton.icon(
            onPressed: onStartTutorial,
            icon: const Icon(Icons.school_outlined, size: 18),
            label: const Text('Обучение'),
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFF5546F7),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 14),
            ),
          )
        : IconButton(
            tooltip: 'Обучение',
            onPressed: onStartTutorial,
            icon: const Icon(Icons.school_outlined),
            color: const Color(0xFF5546F7),
          );
    final Widget dataMenu = PopupMenuButton<_PlannerMenuAction>(
      key: dataKey,
      tooltip: 'Данные',
      onSelected: onMenuAction,
      icon: const Icon(Icons.more_horiz),
      style: IconButton.styleFrom(
        minimumSize: const Size(44, 44),
        backgroundColor: const Color(0xFFFAFBFE),
        side: const BorderSide(color: Color(0xFFE5E8F0)),
      ),
      itemBuilder: (_) => const <PopupMenuEntry<_PlannerMenuAction>>[
        PopupMenuItem<_PlannerMenuAction>(
          value: _PlannerMenuAction.groups,
          child: ListTile(
            leading: Icon(Icons.palette_outlined),
            title: Text('Группы и цвета'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
        PopupMenuDivider(),
        PopupMenuItem<_PlannerMenuAction>(
          value: _PlannerMenuAction.export,
          child: ListTile(
            leading: Icon(Icons.file_download_outlined),
            title: Text('Экспорт JSON'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
        PopupMenuItem<_PlannerMenuAction>(
          value: _PlannerMenuAction.import,
          child: ListTile(
            leading: Icon(Icons.file_upload_outlined),
            title: Text('Импорт JSON'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
        PopupMenuDivider(),
        PopupMenuItem<_PlannerMenuAction>(
          value: _PlannerMenuAction.deleteAll,
          child: ListTile(
            leading: Icon(Icons.delete_sweep_outlined),
            title: Text('Удалить все задачи'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
      ],
    );
    final Widget addButton = Semantics(
      label: 'Новая задача',
      button: true,
      child: compact
          ? IconButton(
              key: addKey,
              tooltip: 'Новая задача',
              onPressed: viewModel.isSaving || readOnly ? null : onCreateTask,
              icon: const Icon(Icons.add, color: Colors.white, size: 25),
              style: IconButton.styleFrom(
                minimumSize: const Size(46, 46),
                backgroundColor: const Color(0xFF5546F7),
                disabledBackgroundColor: const Color(0xFFAAA4E8),
                shape: const CircleBorder(),
              ),
            )
          : Tooltip(
              message: 'Новая задача',
              child: FilledButton.icon(
                key: addKey,
                onPressed: viewModel.isSaving || readOnly ? null : onCreateTask,
                icon: const Icon(Icons.add, size: 19),
                label: const Text('Новая задача'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 17,
                    vertical: 14,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(13),
                  ),
                ),
              ),
            ),
    );

    return Container(
      key: const ValueKey<String>('planner-header'),
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 14 : 18,
        vertical: compact ? 12 : 10,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE8EBF2)),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: Color(0x0D25315A),
            blurRadius: 18,
            offset: Offset(0, 5),
          ),
        ],
      ),
      child: compact
          ? Column(
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(child: logo),
                    compactTutorialButton,
                    const SizedBox(width: 4),
                    dataMenu,
                    const SizedBox(width: 8),
                    addButton,
                  ],
                ),
                if (userSelector != null) ...<Widget>[
                  const SizedBox(height: 14),
                  userSelector,
                ],
                const SizedBox(height: 14),
                search,
                const SizedBox(height: 12),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: navigation,
                ),
              ],
            )
          : medium
          ? Column(
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(child: logo),
                    if (userSelector != null) ...<Widget>[
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 250),
                        child: userSelector,
                      ),
                      const SizedBox(width: 10),
                    ],
                    tutorialButton,
                    const SizedBox(width: 8),
                    dataMenu,
                    const SizedBox(width: 8),
                    addButton,
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: navigation,
                      ),
                    ),
                    const SizedBox(width: 14),
                    search,
                  ],
                ),
              ],
            )
          : Row(
              children: <Widget>[
                logo,
                const SizedBox(width: 22),
                navigation,
                const Spacer(),
                if (userSelector != null) ...<Widget>[
                  userSelector,
                  const SizedBox(width: 10),
                ],
                search,
                const SizedBox(width: 10),
                tutorialButton,
                const SizedBox(width: 10),
                dataMenu,
                const SizedBox(width: 10),
                addButton,
              ],
            ),
    );
  }
}

class _UserCalendarSelector extends StatelessWidget {
  const _UserCalendarSelector({
    required this.users,
    required this.selectedUserId,
    required this.onSelected,
  });

  final List<PlannerUser> users;
  final String selectedUserId;
  final ValueChanged<String>? onSelected;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey<String>('user-calendar-selector'),
      constraints: const BoxConstraints(maxWidth: 260),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F7FF),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: const Color(0xFFDCD8FF)),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          key: const ValueKey<String>('user-calendar-dropdown'),
          value: selectedUserId,
          isExpanded: true,
          icon: const Icon(Icons.expand_more, color: Color(0xFF5546F7)),
          items: users
              .map(
                (PlannerUser user) => DropdownMenuItem<String>(
                  value: user.id,
                  child: Row(
                    children: <Widget>[
                      Icon(
                        user.role == 'admin'
                            ? Icons.admin_panel_settings_outlined
                            : Icons.person_outline,
                        size: 18,
                        color: const Color(0xFF5546F7),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          user.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              )
              .toList(growable: false),
          onChanged: onSelected == null
              ? null
              : (String? value) {
                  if (value != null) onSelected!(value);
                },
        ),
      ),
    );
  }
}

class _HeaderNavigation extends StatelessWidget {
  const _HeaderNavigation({
    required this.selected,
    required this.onSelected,
    required this.onOpenFinance,
    required this.onOpenAdmin,
    super.key,
  });

  final TaskStatusFilter selected;
  final ValueChanged<TaskStatusFilter> onSelected;
  final VoidCallback? onOpenFinance;
  final VoidCallback? onOpenAdmin;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _NavigationButton(
          icon: Icons.calendar_today_outlined,
          label: 'Календарь',
          selected: selected == TaskStatusFilter.all,
          onPressed: () => onSelected(TaskStatusFilter.all),
        ),
        _NavigationButton(
          icon: Icons.check_box_outlined,
          label: 'Активные',
          selected: selected == TaskStatusFilter.active,
          onPressed: () => onSelected(TaskStatusFilter.active),
        ),
        _NavigationButton(
          icon: Icons.fact_check_outlined,
          label: 'Выполненные',
          selected: selected == TaskStatusFilter.completed,
          onPressed: () => onSelected(TaskStatusFilter.completed),
        ),
        if (onOpenFinance != null)
          _NavigationButton(
            icon: Icons.account_balance_wallet_outlined,
            label: 'Финансы',
            selected: false,
            onPressed: onOpenFinance!,
          ),
        if (onOpenAdmin != null)
          _NavigationButton(
            icon: Icons.admin_panel_settings_outlined,
            label: 'Админ',
            selected: false,
            onPressed: onOpenAdmin!,
          ),
      ],
    );
  }
}

class _NavigationButton extends StatelessWidget {
  const _NavigationButton({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 4),
      child: TextButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 19),
        label: Text(label),
        style: TextButton.styleFrom(
          foregroundColor: selected
              ? const Color(0xFF5546F7)
              : const Color(0xFF30364A),
          backgroundColor: selected
              ? const Color(0xFFF1EFFF)
              : Colors.transparent,
          padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(13),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}

class _CalendarPanel extends StatelessWidget {
  const _CalendarPanel({
    required this.viewModel,
    required this.fillAvailableHeight,
    super.key,
  });

  final PlannerViewModel viewModel;
  final bool fillAvailableHeight;

  Color _taskColor(PlannerTask task) {
    final TaskGroup? group = viewModel.groupById(task.groupId);
    if (group != null) return group.color;
    return switch (task.priority) {
      TaskPriority.low => const Color(0xFF21B657),
      TaskPriority.normal => const Color(0xFF2F7CF6),
      TaskPriority.high => const Color(0xFFFF4545),
    };
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE8EAF1)),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: Color(0x0925315A),
            blurRadius: 18,
            offset: Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: fillAvailableHeight ? MainAxisSize.max : MainAxisSize.min,
        children: <Widget>[
          _MonthToolbar(viewModel: viewModel),
          if (fillAvailableHeight)
            Expanded(
              child: CalendarGrid(
                month: viewModel.displayedMonth,
                selectedDate: viewModel.selectedDate,
                today: DateTime.now(),
                tasksForDate: viewModel.tasksForDate,
                taskColor: _taskColor,
                onDateSelected: viewModel.selectDate,
                fillAvailableHeight: true,
              ),
            )
          else
            CalendarGrid(
              month: viewModel.displayedMonth,
              selectedDate: viewModel.selectedDate,
              today: DateTime.now(),
              tasksForDate: viewModel.tasksForDate,
              taskColor: _taskColor,
              onDateSelected: viewModel.selectDate,
            ),
        ],
      ),
    );
  }
}

class _MonthToolbar extends StatelessWidget {
  const _MonthToolbar({required this.viewModel});

  final PlannerViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final bool narrow = constraints.maxWidth < 720;
        final Widget navigation = Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _ToolbarIconButton(
              tooltip: 'Предыдущий месяц',
              icon: Icons.arrow_back,
              onPressed: viewModel.showPreviousMonth,
            ),
            const SizedBox(width: 8),
            _ToolbarIconButton(
              tooltip: 'Следующий месяц',
              icon: Icons.arrow_forward,
              onPressed: viewModel.showNextMonth,
            ),
            const SizedBox(width: 12),
            OutlinedButton(
              onPressed: viewModel.showCurrentMonth,
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF22273A),
                side: const BorderSide(color: Color(0xFFE0E4ED)),
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 15,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(11),
                ),
              ),
              child: const Text('Сегодня'),
            ),
          ],
        );
        final Widget title = Text(
          formatMonthTitle(viewModel.displayedMonth.firstDay),
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            color: const Color(0xFF101426),
            fontWeight: FontWeight.w900,
            letterSpacing: -0.5,
          ),
        );
        final Widget summary = Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _SummaryPill(
              label: '${viewModel.displayedMonthTotalCount} задач',
              color: const Color(0xFF5546F7),
            ),
            const SizedBox(width: 8),
            _SummaryPill(
              label: '${viewModel.displayedMonthCompletedCount} выполнено',
              color: const Color(0xFF21B657),
            ),
          ],
        );

        return Padding(
          padding: EdgeInsets.symmetric(
            horizontal: narrow ? 12 : 20,
            vertical: 16,
          ),
          child: narrow
              ? Column(
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Expanded(child: title),
                        navigation,
                      ],
                    ),
                    const SizedBox(height: 12),
                    summary,
                  ],
                )
              : Row(
                  children: <Widget>[
                    navigation,
                    Expanded(child: title),
                    summary,
                  ],
                ),
        );
      },
    );
  }
}

class _ToolbarIconButton extends StatelessWidget {
  const _ToolbarIconButton({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: tooltip,
      onPressed: onPressed,
      icon: Icon(icon, size: 20),
      style: IconButton.styleFrom(
        minimumSize: const Size(44, 44),
        foregroundColor: const Color(0xFF22273A),
        side: const BorderSide(color: Color(0xFFE0E4ED)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
      ),
    );
  }
}

class _SummaryPill extends StatelessWidget {
  const _SummaryPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: color,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
