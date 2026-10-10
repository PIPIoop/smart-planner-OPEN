import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'features/finance/application/finance_view_model.dart';
import 'features/finance/presentation/finance_page.dart';
import 'features/planner/application/planner_view_model.dart';
import 'features/planner/domain/planner_user.dart';
import 'features/planner/presentation/planner_page.dart';
import 'features/subscription/application/admin_subscription_view_model.dart';
import 'features/subscription/presentation/admin_subscription_page.dart';

class SmartPlannerApp extends StatelessWidget {
  const SmartPlannerApp({
    required this.viewModel,
    this.financeViewModel,
    this.users = const <PlannerUser>[],
    this.adminUsers = const <PlannerUser>[],
    this.selectedUserId,
    this.onUserSelected,
    this.adminSubscriptionViewModel,
    this.adminUserId,
    super.key,
  });

  final PlannerViewModel viewModel;
  final FinanceViewModel? financeViewModel;
  final List<PlannerUser> users;
  final List<PlannerUser> adminUsers;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;
  final AdminSubscriptionViewModel? adminSubscriptionViewModel;
  final String? adminUserId;

  @override
  Widget build(BuildContext context) {
    const Color primary = Color(0xFF5B47F7);
    final ColorScheme scheme =
        ColorScheme.fromSeed(
          seedColor: primary,
          brightness: Brightness.light,
          surface: const Color(0xFFF8F9FD),
        ).copyWith(
          primary: primary,
          secondary: const Color(0xFF7662FF),
          outline: const Color(0xFFDFE3EC),
          outlineVariant: const Color(0xFFECEEF4),
          surfaceContainerLowest: Colors.white,
          surfaceContainerLow: const Color(0xFFFBFCFF),
          surfaceContainer: const Color(0xFFF5F6FB),
        );

    final OutlineInputBorder inputBorder = OutlineInputBorder(
      borderRadius: BorderRadius.circular(14),
      borderSide: const BorderSide(color: Color(0xFFDFE2EC)),
    );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Smart Planner',
      locale: const Locale('ru'),
      supportedLocales: const <Locale>[Locale('ru'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      themeMode: ThemeMode.light,
      theme: ThemeData(
        colorScheme: scheme,
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF6F7FB),
        fontFamily: 'Segoe UI',
        dividerColor: const Color(0xFFE9EBF2),
        splashFactory: InkSparkle.splashFactory,
        textTheme: const TextTheme(
          headlineSmall: TextStyle(letterSpacing: -0.4),
          titleLarge: TextStyle(letterSpacing: -0.3),
          titleMedium: TextStyle(letterSpacing: -0.15),
        ),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 0,
          margin: EdgeInsets.zero,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Color(0xFFE9EBF2)),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFFFDFDFF),
          border: inputBorder,
          enabledBorder: inputBorder,
          focusedBorder: inputBorder.copyWith(
            borderSide: const BorderSide(color: primary, width: 1.6),
          ),
          errorBorder: inputBorder.copyWith(
            borderSide: const BorderSide(color: Color(0xFFE04B4B)),
          ),
          focusedErrorBorder: inputBorder.copyWith(
            borderSide: const BorderSide(color: Color(0xFFE04B4B), width: 1.6),
          ),
          labelStyle: const TextStyle(color: Color(0xFF5E6376)),
          hintStyle: const TextStyle(color: Color(0xFFA0A5B7)),
          prefixIconColor: const Color(0xFF6B5AF3),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 18,
            vertical: 17,
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: primary,
            foregroundColor: Colors.white,
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: primary,
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        checkboxTheme: CheckboxThemeData(
          shape: const CircleBorder(),
          side: const BorderSide(color: Color(0xFFCDD2DE), width: 1.5),
          fillColor: WidgetStateProperty.resolveWith<Color?>((states) {
            if (states.contains(WidgetState.selected)) return primary;
            return null;
          }),
        ),
        switchTheme: SwitchThemeData(
          thumbColor: WidgetStateProperty.resolveWith<Color?>((states) {
            if (states.contains(WidgetState.selected)) return Colors.white;
            return const Color(0xFFFFFFFF);
          }),
          trackColor: WidgetStateProperty.resolveWith<Color?>((states) {
            if (states.contains(WidgetState.selected)) return primary;
            return const Color(0xFFD9DCE6);
          }),
        ),
        tooltipTheme: TooltipThemeData(
          decoration: BoxDecoration(
            color: const Color(0xFF171A2C),
            borderRadius: BorderRadius.circular(10),
          ),
          textStyle: const TextStyle(color: Colors.white),
        ),
      ),
      home: _SmartPlannerHome(
        viewModel: viewModel,
        financeViewModel: financeViewModel,
        users: users,
        adminUsers: adminUsers,
        selectedUserId: selectedUserId,
        onUserSelected: onUserSelected,
        adminSubscriptionViewModel: adminSubscriptionViewModel,
        adminUserId: adminUserId,
      ),
    );
  }
}

class _SmartPlannerHome extends StatefulWidget {
  const _SmartPlannerHome({
    required this.viewModel,
    required this.financeViewModel,
    required this.users,
    required this.adminUsers,
    required this.selectedUserId,
    required this.onUserSelected,
    required this.adminSubscriptionViewModel,
    required this.adminUserId,
  });

  final PlannerViewModel viewModel;
  final FinanceViewModel? financeViewModel;
  final List<PlannerUser> users;
  final List<PlannerUser> adminUsers;
  final String? selectedUserId;
  final ValueChanged<String>? onUserSelected;
  final AdminSubscriptionViewModel? adminSubscriptionViewModel;
  final String? adminUserId;

  @override
  State<_SmartPlannerHome> createState() => _SmartPlannerHomeState();
}

enum _AppSection { planner, finance, admin }

class _SmartPlannerHomeState extends State<_SmartPlannerHome> {
  _AppSection _section = _AppSection.planner;

  bool get _adminViewingAnotherUser =>
      widget.adminUserId != null &&
      widget.selectedUserId != null &&
      widget.selectedUserId != widget.adminUserId;

  @override
  Widget build(BuildContext context) {
    final FinanceViewModel? financeViewModel = widget.financeViewModel;
    final AdminSubscriptionViewModel? adminVm =
        widget.adminSubscriptionViewModel;

    if (_section == _AppSection.admin && adminVm != null) {
      return AdminSubscriptionPage(
        viewModel: adminVm,
        users: widget.adminUsers,
        initialUserId: widget.selectedUserId == widget.adminUserId
            ? null
            : widget.selectedUserId,
        onOpenPlanner: () => setState(() => _section = _AppSection.planner),
        onUserSelected: widget.onUserSelected,
        onOpenFinance: financeViewModel == null
            ? null
            : () => setState(() => _section = _AppSection.finance),
      );
    }

    if (_section == _AppSection.finance && financeViewModel != null) {
      return FinancePage(
        viewModel: financeViewModel,
        onOpenPlanner: () => setState(() => _section = _AppSection.planner),
        onOpenAdmin: adminVm == null
            ? null
            : () => setState(() => _section = _AppSection.admin),
        users: widget.users,
        selectedUserId: widget.selectedUserId,
        onUserSelected: widget.onUserSelected,
        readOnly: _adminViewingAnotherUser,
      );
    }

    return PlannerPage(
      viewModel: widget.viewModel,
      users: widget.users,
      selectedUserId: widget.selectedUserId,
      onUserSelected: widget.onUserSelected,
      onOpenFinance: financeViewModel == null
          ? null
          : () => setState(() => _section = _AppSection.finance),
      onOpenAdmin: adminVm == null
          ? null
          : () => setState(() => _section = _AppSection.admin),
      readOnly: _adminViewingAnotherUser,
    );
  }
}
