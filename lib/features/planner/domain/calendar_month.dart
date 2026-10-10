final class CalendarMonth {
  CalendarMonth(DateTime value) : firstDay = DateTime(value.year, value.month);

  final DateTime firstDay;

  int get year => firstDay.year;
  int get month => firstDay.month;

  CalendarMonth previous() {
    return CalendarMonth(DateTime(year, month - 1));
  }

  CalendarMonth next() {
    return CalendarMonth(DateTime(year, month + 1));
  }

  bool contains(DateTime date) {
    return date.year == year && date.month == month;
  }

  List<DateTime> get visibleDays {
    final int leadingDays = firstDay.weekday - DateTime.monday;
    final DateTime gridStart = DateTime(year, month, 1 - leadingDays);

    return List<DateTime>.generate(
      42,
      (int index) =>
          DateTime(gridStart.year, gridStart.month, gridStart.day + index),
      growable: false,
    );
  }
}
