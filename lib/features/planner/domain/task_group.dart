import 'package:flutter/material.dart';

const List<String> taskGroupColorPalette = <String>[
  '#6C63FF',
  '#3B82F6',
  '#14B8A6',
  '#22C55E',
  '#84CC16',
  '#F59E0B',
  '#F97316',
  '#EF4444',
  '#EC4899',
  '#A855F7',
  '#64748B',
  '#0EA5E9',
];

final class TaskGroupDraft {
  TaskGroupDraft({required String name, required String colorHex})
    : name = _normalizeName(name),
      colorHex = _normalizeColor(colorHex);
  final String name;
  final String colorHex;
}

final class TaskGroup {
  TaskGroup({
    required this.id,
    required String name,
    required String colorHex,
    required this.createdAt,
    required this.updatedAt,
  }) : name = _normalizeName(name),
       colorHex = _normalizeColor(colorHex) {
    if (id.trim().isEmpty) throw ArgumentError('Group ID cannot be empty');
  }
  factory TaskGroup.create({
    required String id,
    required TaskGroupDraft draft,
    required DateTime now,
  }) {
    final DateTime timestamp = now.toUtc();
    return TaskGroup(
      id: id,
      name: draft.name,
      colorHex: draft.colorHex,
      createdAt: timestamp,
      updatedAt: timestamp,
    );
  }
  factory TaskGroup.fromJson(Map<String, Object?> json) => TaskGroup(
    id: json['id']! as String,
    name: json['name']! as String,
    colorHex: json['colorHex']! as String,
    createdAt: DateTime.parse(json['createdAt']! as String),
    updatedAt: DateTime.parse(json['updatedAt']! as String),
  );
  final String id;
  final String name;
  final String colorHex;
  final DateTime createdAt;
  final DateTime updatedAt;
  Color get color => colorFromHex(colorHex);
  TaskGroup applyDraft(TaskGroupDraft draft, DateTime now) => TaskGroup(
    id: id,
    name: draft.name,
    colorHex: draft.colorHex,
    createdAt: createdAt,
    updatedAt: now.toUtc(),
  );
  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'name': name,
    'colorHex': colorHex,
    'createdAt': createdAt.toUtc().toIso8601String(),
    'updatedAt': updatedAt.toUtc().toIso8601String(),
  };
}

Color colorFromHex(String value) {
  final String normalized = _normalizeColor(value);
  return Color(int.parse('FF${normalized.substring(1)}', radix: 16));
}

String _normalizeName(String value) {
  final String normalized = value.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (normalized.isEmpty || normalized.length > 60) {
    throw ArgumentError('Название группы должно содержать 1–60 символов');
  }
  return normalized;
}

String _normalizeColor(String value) {
  final String normalized = value.trim().toUpperCase();
  if (!RegExp(r'^#[0-9A-F]{6}$').hasMatch(normalized)) {
    throw ArgumentError('Цвет группы должен быть в формате #RRGGBB');
  }
  return normalized;
}
