import 'package:flutter/foundation.dart';

import '../data/subscription_admin_repository.dart';
import '../domain/subscription_models.dart';

enum AdminSubscriptionLoadState { idle, loading, ready, error }

final class AdminSubscriptionViewModel extends ChangeNotifier {
  AdminSubscriptionViewModel({required SubscriptionAdminRepository repository})
    : _repository = repository;

  final SubscriptionAdminRepository _repository;
  AdminSubscriptionLoadState loadState = AdminSubscriptionLoadState.idle;
  SubscriptionSnapshot? snapshot;
  List<SubscriptionAuditRecord> audit = const <SubscriptionAuditRecord>[];
  String? errorMessage;
  String? selectedUserId;
  bool saving = false;

  Future<void> selectUser(String userId) async {
    selectedUserId = userId;
    loadState = AdminSubscriptionLoadState.loading;
    errorMessage = null;
    notifyListeners();
    try {
      snapshot = await _repository.loadSubscription(userId);
      audit = await _repository.loadSubscriptionAudit(userId);
      loadState = AdminSubscriptionLoadState.ready;
    } on Object catch (error) {
      errorMessage = error.toString();
      loadState = AdminSubscriptionLoadState.error;
    }
    notifyListeners();
  }

  Future<void> changePlan({
    required String plan,
    required String billingPeriod,
    DateTime? expiresAt,
  }) async {
    final userId = selectedUserId;
    if (userId == null) {
      return;
    }
    await _mutate(
      () => _repository.updateSubscription(
        userId: userId,
        plan: plan,
        status: 'active',
        billingPeriod: billingPeriod,
        expiresAt: expiresAt,
      ),
    );
  }

  Future<void> resetToFree() async {
    final userId = selectedUserId;
    if (userId == null) {
      return;
    }
    await _mutate(() => _repository.resetSubscription(userId));
  }

  Future<void> grantTrial(int days) async {
    final userId = selectedUserId;
    if (userId == null) {
      return;
    }
    await _mutate(() => _repository.grantTrial(userId, days));
  }

  Future<void> grantEntitlement({
    required String key,
    required bool value,
    required DateTime expiresAt,
    String reason = '',
  }) async {
    final userId = selectedUserId;
    if (userId == null) {
      return;
    }
    await _mutate(
      () => _repository.grantEntitlementOverride(
        userId: userId,
        key: key,
        value: value,
        expiresAt: expiresAt,
        reason: reason,
      ),
    );
  }

  Future<void> grantLimitBonus({
    required String key,
    required int amount,
    required DateTime expiresAt,
    String reason = '',
  }) async {
    final userId = selectedUserId;
    if (userId == null) {
      return;
    }
    await _mutate(
      () => _repository.grantLimitBonus(
        userId: userId,
        key: key,
        amount: amount,
        expiresAt: expiresAt,
        reason: reason,
      ),
    );
  }

  Future<void> removeOverride(String overrideId) async {
    final userId = selectedUserId;
    if (userId == null) {
      return;
    }
    await _mutate(() => _repository.deleteOverride(userId, overrideId));
  }

  Future<void> _mutate(Future<void> Function() action) async {
    if (saving) {
      return;
    }
    saving = true;
    errorMessage = null;
    notifyListeners();
    try {
      await action();
      final userId = selectedUserId;
      if (userId != null) {
        snapshot = await _repository.loadSubscription(userId);
        audit = await _repository.loadSubscriptionAudit(userId);
        loadState = AdminSubscriptionLoadState.ready;
      }
    } on Object catch (error) {
      errorMessage = error.toString();
    } finally {
      saving = false;
      notifyListeners();
    }
  }
}
