import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/constants/api_constants.dart';
import '../../core/services/driver_diesel_session_service.dart';
import '../../core/services/offline_tower_diesel_queue_service.dart';
import '../providers/auth_provider.dart';
import '../providers/driver_provider.dart';
import '../screens/driver/tower_diesel_entry_screen.dart';

class NetworkConnectionGate extends StatefulWidget {
  const NetworkConnectionGate({
    super.key,
    required this.child,
    this.probeInterval = const Duration(seconds: 4),
  });

  final Widget child;
  final Duration probeInterval;

  @override
  State<NetworkConnectionGate> createState() => _NetworkConnectionGateState();
}

class _NetworkConnectionGateState extends State<NetworkConnectionGate>
    with WidgetsBindingObserver {
  Timer? _probeTimer;
  bool _isOffline = false;
  bool _isChecking = false;
  bool _probeInFlight = false;
  bool _offlineDieselQueueOpen = false;
  bool _syncInFlight = false;
  int _consecutiveFailures = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(DriverDieselSessionService.instance.initialize());
    unawaited(OfflineTowerDieselQueueService.instance.initialize());
    unawaited(_checkConnection());
    _probeTimer = Timer.periodic(widget.probeInterval, (_) {
      unawaited(_checkConnection());
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _probeTimer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_checkConnection(forceBusyState: _isOffline));
    }
  }

  Future<void> _checkConnection({bool forceBusyState = false}) async {
    if (_probeInFlight || !mounted) {
      return;
    }
    _probeInFlight = true;
    if ((_isOffline || forceBusyState) && mounted) {
      setState(() {
        _isChecking = true;
      });
    }

    final hasConnection = await _canReachBackend();
    if (!mounted) {
      _probeInFlight = false;
      return;
    }

    final wasOffline = _isOffline;
    final hasPendingQueue =
        OfflineTowerDieselQueueService.instance.pendingCount.value > 0;
    setState(() {
      if (hasConnection) {
        _consecutiveFailures = 0;
        _isOffline = false;
      } else {
        _consecutiveFailures += 1;
        final shouldShowOffline =
            _isOffline || forceBusyState || _consecutiveFailures >= 2;
        if (shouldShowOffline) {
          _isOffline = true;
        }
      }
      _isChecking = false;
    });
    _probeInFlight = false;

    if (!wasOffline && _isOffline && mounted) {
      return;
    }
    if (hasConnection && (wasOffline || hasPendingQueue)) {
      unawaited(_syncQueuedDieselEntries());
    }
  }

  Future<bool> _canReachBackend() async {
    final uri = Uri.tryParse(ApiConstants.baseUrl);
    if (uri == null || uri.host.isEmpty) {
      return true;
    }

    final port = uri.hasPort ? uri.port : (uri.scheme == 'http' ? 80 : 443);
    Socket? socket;
    try {
      socket = await Socket.connect(
        uri.host,
        port,
        timeout: const Duration(seconds: 3),
      );
      return true;
    } catch (_) {
      return false;
    } finally {
      socket?.destroy();
    }
  }

  Future<void> _syncQueuedDieselEntries() async {
    if (_syncInFlight || !mounted) {
      return;
    }
    final auth = context.read<AuthProvider>();
    if (!auth.isLoggedIn) {
      return;
    }
    _syncInFlight = true;
    try {
      final result = await context
          .read<DriverProvider>()
          .syncQueuedTowerDieselRecords(silent: true);
      if (!mounted || result.syncedCount <= 0) {
        return;
      }
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          content: Text(
            result.syncedCount == 1
                ? '1 offline diesel filling synced.'
                : '${result.syncedCount} offline diesel fillings synced.',
          ),
        ),
      );
    } finally {
      _syncInFlight = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final showOverlay = _isOffline || _offlineDieselQueueOpen;

    return Stack(
      children: [
        widget.child,
        IgnorePointer(
          ignoring: !showOverlay,
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            child: showOverlay
                ? ValueListenableBuilder<bool>(
                    valueListenable:
                        DriverDieselSessionService.instance.activeDieselTripStarted,
                    builder: (context, hasActiveDieselTrip, _) {
                  return ValueListenableBuilder<int>(
                        valueListenable:
                            OfflineTowerDieselQueueService.instance.pendingCount,
                        builder: (context, pendingQueueCount, __) {
                          final isLoggedIn =
                              context.read<AuthProvider>().isLoggedIn;
                          final canOpenDieselQueue =
                              isLoggedIn && hasActiveDieselTrip;
                          if (_offlineDieselQueueOpen) {
                            return TowerDieselEntryScreen(
                              offlineQueueOnly: true,
                              onCloseRequested: () {
                                if (!mounted) {
                                  return;
                                }
                                setState(() {
                                  _offlineDieselQueueOpen = false;
                                });
                              },
                            );
                          }

                          return _OfflineConnectionView(
                            checking: _isChecking,
                            canOpenDieselQueue: canOpenDieselQueue,
                            pendingQueueCount: pendingQueueCount,
                            onRetry: () => _checkConnection(forceBusyState: true),
                            onOpenDieselQueue: canOpenDieselQueue
                                ? () {
                                    setState(() {
                                      _offlineDieselQueueOpen = true;
                                    });
                                  }
                                : null,
                          );
                        },
                      );
                    },
                  )
                : const SizedBox.shrink(),
          ),
        ),
      ],
    );
  }
}

class _OfflineConnectionView extends StatelessWidget {
  const _OfflineConnectionView({
    required this.checking,
    required this.onRetry,
    required this.canOpenDieselQueue,
    required this.pendingQueueCount,
    this.onOpenDieselQueue,
  });

  final bool checking;
  final VoidCallback onRetry;
  final bool canOpenDieselQueue;
  final int pendingQueueCount;
  final VoidCallback? onOpenDieselQueue;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox.expand(
      child: ColoredBox(
        color: const Color(0xFFF8FAFC),
        child: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 360),
                child: Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: const Color(0xFFD7E2E1)),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.08),
                        blurRadius: 24,
                        offset: const Offset(0, 12),
                      ),
                    ],
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 72,
                        height: 72,
                        decoration: BoxDecoration(
                          color: const Color(0xFFDBEAFE),
                          borderRadius: BorderRadius.circular(22),
                        ),
                        child: const Icon(
                          Icons.wifi_off_rounded,
                          color: Color(0xFF2563EB),
                          size: 36,
                        ),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'No internet connection',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: const Color(0xFF111827),
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'We will keep trying automatically. This page will close as soon as the connection is back.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: const Color(0xFF4B5563),
                          height: 1.4,
                        ),
                      ),
                      if (pendingQueueCount > 0) ...[
                        const SizedBox(height: 12),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE6F4EA),
                            borderRadius: BorderRadius.circular(16),
                            border:
                                Border.all(color: const Color(0xFF9AD7B0)),
                          ),
                          child: Text(
                            pendingQueueCount == 1
                                ? '1 diesel filling is waiting to sync.'
                                : '$pendingQueueCount diesel fillings are waiting to sync.',
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                              color: const Color(0xFF166534),
                            ),
                          ),
                        ),
                      ],
                      const SizedBox(height: 18),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          FilledButton.icon(
                            onPressed: checking ? null : onRetry,
                            icon: checking
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(
                                        Colors.white,
                                      ),
                                    ),
                                  )
                                : const Icon(Icons.refresh_rounded),
                            label: Text(
                              checking ? 'Checking...' : 'Try Again',
                            ),
                          ),
                          if (canOpenDieselQueue) ...[
                            const SizedBox(height: 10),
                            OutlinedButton.icon(
                              onPressed:
                                  checking ? null : onOpenDieselQueue,
                              icon: const Icon(Icons.local_gas_station_outlined),
                              label: const Text('Open Diesel Queue'),
                            ),
                          ],
                        ],
                      ),
                      if (canOpenDieselQueue) ...[
                        const SizedBox(height: 10),
                        Text(
                          'You can keep saving tower diesel entries offline while the diesel trip is active.',
                          textAlign: TextAlign.center,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: const Color(0xFF64748B),
                            height: 1.35,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
