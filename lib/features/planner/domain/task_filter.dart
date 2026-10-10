enum TaskStatusFilter {
  all,
  active,
  completed;

  String get label => switch (this) {
    TaskStatusFilter.all => 'Все',
    TaskStatusFilter.active => 'Активные',
    TaskStatusFilter.completed => 'Выполненные',
  };
}

enum ImportMode {
  merge,
  replace;

  String get label => switch (this) {
    ImportMode.merge => 'Объединить',
    ImportMode.replace => 'Заменить всё',
  };
}
