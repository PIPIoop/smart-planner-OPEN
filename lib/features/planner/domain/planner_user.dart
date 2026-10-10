final class PlannerUser {
  const PlannerUser({
    required this.id,
    required this.displayName,
    required this.role,
    required this.status,
    this.username,
    this.subscriptionPlan = 'free',
    this.subscriptionStatus = 'active',
    this.billingPeriod = 'manual',
    this.subscriptionExpiresAt,
    this.trialEndsAt,
    this.taskCount = 0,
    this.goalCount = 0,
    this.groupCount = 0,
  });

  factory PlannerUser.fromJson(Map<String, Object?> json) {
    return PlannerUser(
      id: json['telegramUserId'] as String,
      displayName: json['displayName'] as String,
      username: json['username'] as String?,
      role: json['role'] as String,
      status: json['status'] as String,
      subscriptionPlan: json['subscriptionPlan'] as String? ?? 'free',
      subscriptionStatus: json['subscriptionStatus'] as String? ?? 'active',
      billingPeriod: json['billingPeriod'] as String? ?? 'manual',
      subscriptionExpiresAt: _parseDate(json['subscriptionExpiresAt']),
      trialEndsAt: _parseDate(json['trialEndsAt']),
      taskCount: (json['taskCount'] as num?)?.toInt() ?? 0,
      goalCount: (json['goalCount'] as num?)?.toInt() ?? 0,
      groupCount: (json['groupCount'] as num?)?.toInt() ?? 0,
    );
  }

  final String id;
  final String displayName;
  final String? username;
  final String role;
  final String status;
  final String subscriptionPlan;
  final String subscriptionStatus;
  final String billingPeriod;
  final DateTime? subscriptionExpiresAt;
  final DateTime? trialEndsAt;
  final int taskCount;
  final int goalCount;
  final int groupCount;

  String get label =>
      username == null ? displayName : '$displayName (@$username)';

  String get planLabel => switch (subscriptionPlan) {
    'plus' => 'Plus',
    'full' => 'Full',
    _ => 'Free',
  };
}

DateTime? _parseDate(Object? value) {
  if (value is! String || value.isEmpty) {
    return null;
  }
  return DateTime.tryParse(value)?.toLocal();
}
