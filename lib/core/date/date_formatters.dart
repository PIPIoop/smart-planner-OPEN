import '../../features/planner/domain/planner_task.dart';

const List<String> _monthNames = <String>[
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
];

const List<String> _monthGenitiveNames = <String>[
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
];

const List<String> weekdayShortNames = <String>[
  'Пн',
  'Вт',
  'Ср',
  'Чт',
  'Пт',
  'Сб',
  'Вс',
];

String formatMonthTitle(DateTime date) {
  return '${_monthNames[date.month - 1]} ${date.year}';
}

String formatFullDate(DateTime date) {
  return '${date.day} ${_monthGenitiveNames[date.month - 1]} ${date.year}';
}

String formatShortDate(DateTime date) {
  return '${date.day.toString().padLeft(2, '0')}.'
      '${date.month.toString().padLeft(2, '0')}.'
      '${date.year}';
}

String formatMinutesOfDay(int minutes) {
  final int hours = minutes ~/ 60;
  final int minute = minutes % 60;
  return '${hours.toString().padLeft(2, '0')}:'
      '${minute.toString().padLeft(2, '0')}';
}

String formatTaskTime(PlannerTask task) {
  final int? startMinute = task.startMinute;
  if (startMinute == null) return 'Без времени';
  final int? duration = task.durationMinutes;
  if (duration == null) return formatMinutesOfDay(startMinute);
  return '${formatMinutesOfDay(startMinute)}–${formatMinutesOfDay(startMinute + duration)}';
}
