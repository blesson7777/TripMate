import 'dart:async';

import 'package:flutter/material.dart';

class StaggeredEntrance extends StatefulWidget {
  const StaggeredEntrance({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.duration = const Duration(milliseconds: 520),
    this.initialOffset = const Offset(0, 20),
  });

  final Widget child;
  final Duration delay;
  final Duration duration;
  final Offset initialOffset;

  @override
  State<StaggeredEntrance> createState() => _StaggeredEntranceState();
}

class _StaggeredEntranceState extends State<StaggeredEntrance>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.duration,
    );

    _timer = Timer(widget.delay, () {
      if (!mounted) {
        return;
      }
      _controller.forward();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final curved = Curves.easeOutCubic.transform(_controller.value);
        final dx = widget.initialOffset.dx * (1 - curved);
        final dy = widget.initialOffset.dy * (1 - curved);
        return Opacity(
          opacity: curved,
          child: Transform.translate(
            offset: Offset(dx, dy),
            child: child,
          ),
        );
      },
      child: widget.child,
    );
  }
}
