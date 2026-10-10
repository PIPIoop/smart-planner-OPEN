final class SubscriptionOverride {
  const SubscriptionOverride({
    required this.id,
    required this.key,
    required this.kind,
    required this.expiresAt,
    required this.reason,
    this.boolValue,
    this.intValue,
  });

  factory SubscriptionOverride.fromJson(Map<String, Object?> json) {
    return SubscriptionOverride(
      id: json['id'] as String,
      key: json['key'] as String,
      kind: json['kind'] as String,
      boolValue: json['boolValue'] as bool?,
      intValue: (json['intValue'] as num?)?.toInt(),
      expiresAt: DateTime.parse(json['expiresAt'] as String),
      reason: json['reason'] as String? ?? '',
    );
  }

  final String id;
  final String key;
  final String kind;
  final bool? boolValue;
  final int? intValue;
  final DateTime expiresAt;
  final String reason;
}

final class SubscriptionSnapshot {
  const SubscriptionSnapshot({
    required this.userId,
    required this.plan,
    required this.status,
    required this.billingPeriod,
    required this.entitlements,
    required this.limits,
    required this.publicUnlimited,
    required this.usage,
    required this.overrides,
    required this.financeReadOnly,
    this.expiresAt,
    this.trialEndsAt,
    this.graceEndsAt,
  });

  factory SubscriptionSnapshot.fromJson(Map<String, Object?> json) {
    Map<String, bool> boolMap(Object? value) => value is Map
        ? value.map<String, bool>(
            (dynamic key, dynamic item) =>
                MapEntry<String, bool>(key.toString(), item == true),
          )
        : <String, bool>{};
    Map<String, int> intMap(Object? value) => value is Map
        ? value.map<String, int>(
            (dynamic key, dynamic item) => MapEntry<String, int>(
              key.toString(),
              (item as num?)?.toInt() ?? 0,
            ),
          )
        : <String, int>{};

    return SubscriptionSnapshot(
      userId: json['userId'] as String,
      plan: json['plan'] as String,
      status: json['status'] as String,
      billingPeriod: json['billingPeriod'] as String,
      expiresAt: _date(json['expiresAt']),
      trialEndsAt: _date(json['trialEndsAt']),
      graceEndsAt: _date(json['graceEndsAt']),
      entitlements: boolMap(json['entitlements']),
      limits: intMap(json['limits']),
      publicUnlimited:
          (json['publicUnlimited'] as List<Object?>? ?? const <Object?>[])
              .map((Object? item) => item.toString())
              .toSet(),
      usage: intMap(json['usage']),
      overrides: (json['overrides'] as List<Object?>? ?? const <Object?>[])
          .whereType<Map<String, Object?>>()
          .map(SubscriptionOverride.fromJson)
          .toList(growable: false),
      financeReadOnly: json['financeReadOnly'] as bool? ?? true,
    );
  }

  final String userId;
  final String plan;
  final String status;
  final String billingPeriod;
  final DateTime? expiresAt;
  final DateTime? trialEndsAt;
  final DateTime? graceEndsAt;
  final Map<String, bool> entitlements;
  final Map<String, int> limits;
  final Set<String> publicUnlimited;
  final Map<String, int> usage;
  final List<SubscriptionOverride> overrides;
  final bool financeReadOnly;

  bool has(String entitlement) => entitlements[entitlement] ?? false;
  int limitOf(String key) => limits[key] ?? 0;
  int usageOf(String key) => usage[key] ?? 0;
  bool isPublicUnlimited(String key) => publicUnlimited.contains(key);

  String get planLabel => switch (plan) {
    'plus' => 'Plus',
    'full' => 'Full',
    _ => 'Free',
  };
}

final class SubscriptionAuditRecord {
  const SubscriptionAuditRecord({
    required this.id,
    required this.actorId,
    required this.userId,
    required this.action,
    required this.createdAt,
  });

  factory SubscriptionAuditRecord.fromJson(Map<String, Object?> json) {
    return SubscriptionAuditRecord(
      id: (json['id'] as num).toInt(),
      actorId: json['actorId'] as String,
      userId: json['userId'] as String,
      action: json['action'] as String,
      createdAt: DateTime.parse(json['createdAt'] as String),
    );
  }

  final int id;
  final String actorId;
  final String userId;
  final String action;
  final DateTime createdAt;
}

DateTime? _date(Object? value) {
  if (value is! String || value.isEmpty) {
    return null;
  }
  return DateTime.tryParse(value)?.toLocal();
}
