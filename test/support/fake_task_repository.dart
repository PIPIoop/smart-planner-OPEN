import 'dart:async';

import 'package:smart_planner/features/planner/data/task_repository.dart';
import 'package:smart_planner/features/planner/domain/planner_goal.dart';
import 'package:smart_planner/features/planner/domain/planner_task.dart';
import 'package:smart_planner/features/planner/domain/task_group.dart';

final class FakeTaskRepository implements TaskRepository {
  FakeTaskRepository([List<PlannerTask>? initial])
    : stored = <PlannerTask>[...?initial];

  List<PlannerTask> stored;
  List<PlannerGoal> goals = <PlannerGoal>[];
  List<TaskGroup> groups = <TaskGroup>[];
  Object? loadError;
  Object? saveError;
  Completer<List<PlannerTask>>? nextLoad;

  void _throwIfSavingFails() {
    final Object? error = saveError;
    if (error != null) {
      throw error;
    }
  }

  @override
  Future<List<PlannerTask>> loadAll() async {
    final Completer<List<PlannerTask>>? delayed = nextLoad;
    if (delayed != null) {
      nextLoad = null;
      return delayed.future;
    }
    final Object? error = loadError;
    if (error != null) {
      throw error;
    }
    return <PlannerTask>[...stored];
  }

  @override
  Future<PlannerTask> create(PlannerTask task) async {
    _throwIfSavingFails();
    stored = <PlannerTask>[...stored, task];
    return task;
  }

  @override
  Future<PlannerTask> update(PlannerTask task) async {
    _throwIfSavingFails();
    final int index = stored.indexWhere(
      (PlannerTask item) => item.id == task.id,
    );
    if (index == -1) {
      throw StateError('Task not found');
    }
    stored[index] = task;
    return task;
  }

  @override
  Future<void> delete(String taskId) async {
    _throwIfSavingFails();
    stored.removeWhere((PlannerTask task) => task.id == taskId);
  }

  @override
  Future<List<PlannerGoal>> loadGoals() async => <PlannerGoal>[...goals];

  @override
  Future<void> createGoal(PlannerGoal goal, List<PlannerTask> tasks) async {
    _throwIfSavingFails();
    goals = <PlannerGoal>[...goals, goal];
    stored = <PlannerTask>[...stored, ...tasks];
  }

  @override
  Future<void> deleteGoal(String goalId) async {
    _throwIfSavingFails();
    goals.removeWhere((PlannerGoal goal) => goal.id == goalId);
    stored.removeWhere((PlannerTask task) => task.goalId == goalId);
  }

  @override
  Future<List<TaskGroup>> loadGroups() async => <TaskGroup>[...groups];

  @override
  Future<TaskGroup> createGroup(TaskGroup group) async {
    _throwIfSavingFails();
    groups = <TaskGroup>[...groups, group];
    return group;
  }

  @override
  Future<TaskGroup> updateGroup(TaskGroup group) async {
    _throwIfSavingFails();
    final int index = groups.indexWhere(
      (TaskGroup item) => item.id == group.id,
    );
    if (index == -1) throw StateError('Group not found');
    groups[index] = group;
    return group;
  }

  @override
  Future<void> deleteGroup(String groupId) async {
    _throwIfSavingFails();
    groups.removeWhere((TaskGroup group) => group.id == groupId);
    stored = stored
        .map(
          (PlannerTask task) =>
              task.groupId == groupId ? task.withoutGroup() : task,
        )
        .toList();
  }

  @override
  Future<void> replacePlannerData({
    required List<PlannerTask> tasks,
    required List<PlannerGoal> goals,
    required List<TaskGroup> groups,
  }) async {
    _throwIfSavingFails();
    stored = <PlannerTask>[...tasks];
    this.goals = <PlannerGoal>[...goals];
    this.groups = <TaskGroup>[...groups];
  }

  @override
  Future<void> replaceAll(List<PlannerTask> tasks) async {
    _throwIfSavingFails();
    stored = <PlannerTask>[...tasks];
  }
}
