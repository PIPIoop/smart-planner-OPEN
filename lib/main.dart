import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'core/id/task_id_generator.dart';
import 'features/finance/application/finance_view_model.dart';
import 'features/finance/data/finance_repository.dart';
import 'features/planner/application/planner_view_model.dart';
import 'features/planner/data/local_task_repository.dart';
import 'features/planner/data/remote_task_repository.dart';
import 'features/planner/data/task_repository.dart';
import 'features/planner/domain/planner_user.dart';
import 'features/subscription/application/admin_subscription_view_model.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PlannerBootstrap());
}

class PlannerBootstrap extends StatefulWidget {
  const PlannerBootstrap({super.key});

  @override
  State<PlannerBootstrap> createState() => _PlannerBootstrapState();
}

class _PlannerBootstrapState extends State<PlannerBootstrap> {
  static const String _taskApiUrl = String.fromEnvironment('TASK_API_URL');

  final TextEditingController _passwordController = TextEditingController();
  PlannerViewModel? _viewModel;
  FinanceViewModel? _financeViewModel;
  AdminSubscriptionViewModel? _adminSubscriptionViewModel;
  http.Client? _httpClient;
  RemoteTaskRepository? _remoteRepository;
  Timer? _synchronizationTimer;
  List<PlannerUser> _users = const <PlannerUser>[];
  List<PlannerUser> _adminUsers = const <PlannerUser>[];
  String? _selectedUserId;
  bool _loggingIn = false;
  String? _loginError;

  @override
  void initState() {
    super.initState();
    if (_taskApiUrl.trim().isEmpty) {
      final LocalTaskRepository repository = LocalTaskRepository(
        preferences: SharedPreferencesAsync(),
      );
      _viewModel = _createViewModel(repository);
      _financeViewModel = _createFinanceViewModel(repository);
      unawaited(_viewModel!.initialize());
      unawaited(_financeViewModel!.initialize());
    } else {
      _httpClient = http.Client();
      _remoteRepository = RemoteTaskRepository(
        baseUrl: _taskApiUrl,
        client: _httpClient!,
      );
    }
  }

  PlannerViewModel _createViewModel(TaskRepository repository) {
    return PlannerViewModel(
      repository: repository,
      idGenerator: TaskIdGenerator(),
    );
  }

  FinanceViewModel _createFinanceViewModel(FinanceRepository repository) {
    return FinanceViewModel(
      repository: repository,
      idGenerator: TaskIdGenerator(),
    );
  }

  Future<void> _login() async {
    final RemoteTaskRepository? repository = _remoteRepository;
    if (repository == null || _passwordController.text.isEmpty) return;
    setState(() {
      _loggingIn = true;
      _loginError = null;
    });
    try {
      await repository.loginAdmin(_passwordController.text);
      final List<PlannerUser> adminUsers = await repository.loadAllUsers();
      final List<PlannerUser> users = adminUsers
          .where((PlannerUser user) => user.status == 'active')
          .toList(growable: false);
      final PlannerViewModel viewModel = _createViewModel(repository);
      final FinanceViewModel financeViewModel = _createFinanceViewModel(
        repository,
      );
      final AdminSubscriptionViewModel adminSubscriptionViewModel =
          AdminSubscriptionViewModel(repository: repository);
      if (!mounted) {
        viewModel.dispose();
        financeViewModel.dispose();
        adminSubscriptionViewModel.dispose();
        return;
      }
      setState(() {
        _users = users;
        _adminUsers = adminUsers;
        _selectedUserId = repository.selectedUserId;
        _viewModel = viewModel;
        _financeViewModel = financeViewModel;
        _adminSubscriptionViewModel = adminSubscriptionViewModel;
        _loggingIn = false;
        _passwordController.clear();
      });
      await Future.wait([
        viewModel.initialize(),
        financeViewModel.initialize(),
      ]);
      _synchronizationTimer = Timer.periodic(const Duration(seconds: 2), (_) {
        unawaited(_viewModel?.synchronize());
        unawaited(_financeViewModel?.synchronize());
      });
    } on Object {
      if (mounted) {
        setState(() {
          _loggingIn = false;
          _loginError = 'Не удалось войти. Проверьте пароль и работу API.';
        });
      }
    }
  }

  Future<void> _selectUser(String userId) async {
    final RemoteTaskRepository? repository = _remoteRepository;
    if (repository == null || userId == _selectedUserId) return;

    final PlannerViewModel? previous = _viewModel;
    final FinanceViewModel? previousFinance = _financeViewModel;
    repository.selectUser(userId);
    final PlannerViewModel replacement = _createViewModel(repository);
    final FinanceViewModel financeReplacement = _createFinanceViewModel(
      repository,
    );
    setState(() {
      _selectedUserId = userId;
      _viewModel = replacement;
      _financeViewModel = financeReplacement;
    });
    previous?.dispose();
    previousFinance?.dispose();
    await Future.wait([
      replacement.initialize(),
      financeReplacement.initialize(),
    ]);
    final AdminSubscriptionViewModel? admin = _adminSubscriptionViewModel;
    if (admin != null && userId != repository.adminUserId) {
      await admin.selectUser(userId);
    }
  }

  @override
  void dispose() {
    _synchronizationTimer?.cancel();
    _passwordController.dispose();
    _httpClient?.close();
    _viewModel?.dispose();
    _financeViewModel?.dispose();
    _adminSubscriptionViewModel?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final PlannerViewModel? viewModel = _viewModel;
    final FinanceViewModel? financeViewModel = _financeViewModel;
    if (viewModel == null || financeViewModel == null) {
      return _WebAdminLoginApp(
        controller: _passwordController,
        error: _loginError,
        busy: _loggingIn,
        onLogin: _login,
      );
    }
    return SmartPlannerApp(
      viewModel: viewModel,
      financeViewModel: financeViewModel,
      users: _users,
      adminUsers: _adminUsers,
      selectedUserId: _selectedUserId,
      onUserSelected: (String userId) => unawaited(_selectUser(userId)),
      adminSubscriptionViewModel: _adminSubscriptionViewModel,
      adminUserId: _remoteRepository?.adminUserId,
    );
  }
}

class _WebAdminLoginApp extends StatelessWidget {
  const _WebAdminLoginApp({
    required this.controller,
    required this.error,
    required this.busy,
    required this.onLogin,
  });

  final TextEditingController controller;
  final String? error;
  final bool busy;
  final Future<void> Function() onLogin;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Smart Planner — вход',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF5546F7)),
        useMaterial3: true,
        fontFamily: 'Segoe UI',
      ),
      home: Scaffold(
        backgroundColor: const Color(0xFFF4F6FB),
        body: Center(
          child: Card(
            margin: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: AutofillGroup(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      const Icon(
                        Icons.admin_panel_settings_outlined,
                        size: 54,
                        color: Color(0xFF5546F7),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'Веб-доступ администратора',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        'Введите отдельный веб-пароль из локального .env. Сессия действует 8 часов и не сохраняется в браузере.',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      TextField(
                        key: const ValueKey<String>('web-admin-password'),
                        controller: controller,
                        obscureText: true,
                        enabled: !busy,
                        autofillHints: const <String>[AutofillHints.password],
                        onSubmitted: (_) => onLogin(),
                        decoration: InputDecoration(
                          labelText: 'Пароль администратора',
                          errorText: error,
                          prefixIcon: const Icon(Icons.lock_outline),
                        ),
                      ),
                      const SizedBox(height: 18),
                      FilledButton.icon(
                        key: const ValueKey<String>('web-admin-login'),
                        onPressed: busy ? null : onLogin,
                        icon: busy
                            ? const SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.login),
                        label: Text(busy ? 'Входим…' : 'Войти'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
