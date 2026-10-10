import 'dart:math' as math;

import 'package:flutter/material.dart';

class PlannerTutorialStep {
  const PlannerTutorialStep({
    required this.title,
    required this.description,
    required this.icon,
    required this.targetKey,
  });

  final String title;
  final String description;
  final IconData icon;
  final GlobalKey targetKey;
}

class PlannerTutorialOverlay extends StatelessWidget {
  const PlannerTutorialOverlay({
    required this.step,
    required this.stepIndex,
    required this.stepCount,
    required this.onPrevious,
    required this.onNext,
    required this.onClose,
    super.key,
  });

  final PlannerTutorialStep step;
  final int stepIndex;
  final int stepCount;
  final VoidCallback? onPrevious;
  final VoidCallback onNext;
  final VoidCallback onClose;

  Rect? _targetRect() {
    final BuildContext? targetContext = step.targetKey.currentContext;
    final RenderObject? renderObject = targetContext?.findRenderObject();
    if (renderObject is! RenderBox || !renderObject.hasSize) {
      return null;
    }
    final Offset offset = renderObject.localToGlobal(Offset.zero);
    return offset & renderObject.size;
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final Size viewport = constraints.biggest;
        final Rect fallback = Rect.fromCenter(
          center: viewport.center(Offset.zero),
          width: math.min(320, viewport.width - 32),
          height: 80,
        );
        final Rect target = (_targetRect() ?? fallback).inflate(8);
        final double cardWidth = math.min(380, viewport.width - 32);
        const double estimatedCardHeight = 238;
        final double left = (target.center.dx - cardWidth / 2)
            .clamp(16.0, math.max(16, viewport.width - cardWidth - 16))
            .toDouble();

        double top = target.bottom + 18;
        if (top + estimatedCardHeight > viewport.height - 16) {
          top = target.top - estimatedCardHeight - 18;
        }
        top = top
            .clamp(
              16.0,
              math.max(16, viewport.height - estimatedCardHeight - 16),
            )
            .toDouble();

        return Material(
          color: Colors.transparent,
          child: Stack(
            children: <Widget>[
              Positioned.fill(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {},
                  child: CustomPaint(
                    painter: _SpotlightPainter(target: target),
                  ),
                ),
              ),
              Positioned(
                left: left,
                top: top,
                width: cardWidth,
                child: Semantics(
                  liveRegion: true,
                  label: 'Обучение: ${step.title}',
                  child: Container(
                    key: ValueKey<String>('tutorial-step-$stepIndex'),
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(22),
                      border: Border.all(color: const Color(0xFFE2E5EF)),
                      boxShadow: const <BoxShadow>[
                        BoxShadow(
                          color: Color(0x33212A55),
                          blurRadius: 34,
                          offset: Offset(0, 14),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Container(
                              width: 42,
                              height: 42,
                              decoration: const BoxDecoration(
                                color: Color(0xFFF0EEFF),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                step.icon,
                                color: const Color(0xFF5546F7),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                step.title,
                                style: Theme.of(context).textTheme.titleMedium
                                    ?.copyWith(
                                      color: const Color(0xFF15192B),
                                      fontWeight: FontWeight.w800,
                                    ),
                              ),
                            ),
                            IconButton(
                              tooltip: 'Закрыть обучение',
                              onPressed: onClose,
                              icon: const Icon(Icons.close),
                            ),
                          ],
                        ),
                        const SizedBox(height: 14),
                        Text(
                          step.description,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(
                                color: const Color(0xFF606A82),
                                height: 1.5,
                              ),
                        ),
                        const SizedBox(height: 18),
                        Row(
                          children: <Widget>[
                            Text(
                              '${stepIndex + 1} из $stepCount',
                              style: Theme.of(context).textTheme.labelLarge
                                  ?.copyWith(
                                    color: const Color(0xFF858DA1),
                                    fontWeight: FontWeight.w600,
                                  ),
                            ),
                            const Spacer(),
                            if (onPrevious != null)
                              TextButton(
                                onPressed: onPrevious,
                                child: const Text('Назад'),
                              ),
                            const SizedBox(width: 8),
                            FilledButton(
                              onPressed: onNext,
                              style: FilledButton.styleFrom(
                                backgroundColor: const Color(0xFF5546F7),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 20,
                                  vertical: 14,
                                ),
                              ),
                              child: Text(
                                stepIndex == stepCount - 1 ? 'Готово' : 'Далее',
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _SpotlightPainter extends CustomPainter {
  const _SpotlightPainter({required this.target});

  final Rect target;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect viewport = Offset.zero & size;
    final RRect spotlight = RRect.fromRectAndRadius(
      target.intersect(viewport),
      const Radius.circular(18),
    );

    canvas.saveLayer(viewport, Paint());
    canvas.drawRect(viewport, Paint()..color = const Color(0xB30D1020));
    canvas.drawRRect(
      spotlight,
      Paint()
        ..blendMode = BlendMode.clear
        ..color = Colors.transparent,
    );
    canvas.restore();
    canvas.drawRRect(
      spotlight,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3
        ..color = const Color(0xFF8B7FFF),
    );
  }

  @override
  bool shouldRepaint(_SpotlightPainter oldDelegate) {
    return oldDelegate.target != target;
  }
}
