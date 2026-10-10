import 'dart:math';

final class TaskIdGenerator {
  TaskIdGenerator({Random? random}) : _random = random ?? Random();

  final Random _random;

  String next() {
    final String timestamp = DateTime.now()
        .toUtc()
        .microsecondsSinceEpoch
        .toRadixString(36);
    final String suffix = _random.nextInt(0x7fffffff).toRadixString(36);
    return '$timestamp-$suffix';
  }
}
