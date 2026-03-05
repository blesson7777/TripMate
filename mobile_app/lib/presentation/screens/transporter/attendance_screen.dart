import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class AttendanceScreen extends StatefulWidget {
  const AttendanceScreen({super.key});

  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  DateTime _selectedDate = DateTime.now();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context
          .read<TransporterProvider>()
          .loadDailyAttendance(date: _selectedDate);
    });
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 1),
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _selectedDate = picked;
    });
    if (!mounted) {
      return;
    }
    await context.read<TransporterProvider>().loadDailyAttendance(date: picked);
  }

  Future<void> _markAttendance({
    required int driverId,
    required String status,
  }) async {
    final success = await context.read<TransporterProvider>().markDriverAttendance(
          driverId: driverId,
          status: status,
          date: _selectedDate,
        );
    if (!mounted) {
      return;
    }
    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.read<TransporterProvider>().error ??
                'Unable to update attendance',
          ),
        ),
      );
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Marked $status successfully')),
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'ON_DUTY':
        return const Color(0xFF0A6B6F);
      case 'NO_TRIP':
        return const Color(0xFFE08D3C);
      case 'LEAVE':
      case 'ABSENT':
        return const Color(0xFFCF6E41);
      case 'PRESENT':
        return const Color(0xFF228B8D);
      default:
        return const Color(0xFF6B7280);
    }
  }

  String _dateLabel(DateTime value) {
    final date = value.toIso8601String().split('T').first;
    return date;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Daily Attendance'),
        actions: [
          IconButton(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_month_outlined),
            tooltip: 'Select date',
          ),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE9F2F2), Color(0xFFF5EFE7)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            return RefreshIndicator(
              onRefresh: () => provider.loadDailyAttendance(date: _selectedDate),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                children: [
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.event_outlined),
                      title: const Text('Attendance Date'),
                      subtitle: Text(_dateLabel(_selectedDate)),
                      trailing: TextButton(
                        onPressed: _pickDate,
                        child: const Text('Change'),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (provider.loading && provider.dailyAttendance.isEmpty)
                    const Padding(
                      padding: EdgeInsets.only(top: 30),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (provider.error != null &&
                      provider.dailyAttendance.isEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 20),
                      child: Center(child: Text(provider.error!)),
                    )
                  else if (provider.dailyAttendance.isEmpty)
                    const Padding(
                      padding: EdgeInsets.only(top: 24),
                      child: Center(child: Text('No drivers found.')),
                    )
                  else
                    ...provider.dailyAttendance.asMap().entries.map((entry) {
                      final index = entry.key;
                      final item = entry.value;
                      final statusColor = _statusColor(item.status);
                      return StaggeredEntrance(
                        delay: Duration(milliseconds: 55 * index),
                        child: Card(
                          margin: const EdgeInsets.only(bottom: 10),
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        item.driverName,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                              fontWeight: FontWeight.w700,
                                            ),
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 10,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        color: statusColor.withValues(alpha: 0.12),
                                        borderRadius: BorderRadius.circular(999),
                                      ),
                                      child: Text(
                                        item.status,
                                        style: TextStyle(
                                          color: statusColor,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text('License: ${item.licenseNumber}'),
                                Text(
                                  'Allocated Vehicle: ${item.assignedVehicleNumber ?? "Not assigned"}',
                                ),
                                Text(
                                  'Attendance Vehicle: ${item.attendanceVehicleNumber ?? "Not started"}',
                                ),
                                if (item.startKm != null)
                                  Text(
                                    'Start KM: ${item.startKm}${item.endKm != null ? " | End KM: ${item.endKm}" : ""}',
                                  ),
                                const SizedBox(height: 10),
                                Row(
                                  children: [
                                    FilledButton.tonalIcon(
                                      onPressed: (provider.loading ||
                                              item.hasAttendance)
                                          ? null
                                          : () => _markAttendance(
                                                driverId: item.driverId,
                                                status: 'PRESENT',
                                              ),
                                      icon: const Icon(Icons.check_circle_outline),
                                      label: const Text('Mark Present'),
                                    ),
                                    const SizedBox(width: 10),
                                    FilledButton.tonalIcon(
                                      onPressed: provider.loading
                                          ? null
                                          : () => _markAttendance(
                                                driverId: item.driverId,
                                                status: 'ABSENT',
                                              ),
                                      icon: const Icon(Icons.cancel_outlined),
                                      label: const Text('Mark Absent'),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
