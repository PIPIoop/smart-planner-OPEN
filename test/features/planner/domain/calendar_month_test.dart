import 'package:flutter_test/flutter_test.dart';
import 'package:smart_planner/features/planner/domain/calendar_month.dart';

void main() {
  test('calendar month always exposes a 42-day Monday-first grid', () {
    final CalendarMonth month = CalendarMonth(DateTime(2026, 8, 19));

    expect(month.firstDay, DateTime(2026, 8));
    expect(month.visibleDays, hasLength(42));
    expect(month.visibleDays.first, DateTime(2026, 7, 27));
    expect(month.visibleDays.last, DateTime(2026, 9, 6));
    expect(month.visibleDays.first.weekday, DateTime.monday);
    expect(month.visibleDays.last.weekday, DateTime.sunday);
  });
}
