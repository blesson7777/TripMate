import 'package:flutter/material.dart';

class BusyIndicator extends StatelessWidget {
  const BusyIndicator({super.key, required this.isBusy, required this.child});

  final bool isBusy;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!isBusy) {
      return child;
    }

    return Stack(
      children: [
        child,
        Positioned.fill(
          child: ColoredBox(
            color: Colors.black.withValues(alpha: 0.2),
            child: const Center(child: CircularProgressIndicator()),
          ),
        ),
      ],
    );
  }
}
