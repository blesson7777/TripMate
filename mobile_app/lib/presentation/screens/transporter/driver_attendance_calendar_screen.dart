import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/attendance_calendar.dart';
import '../../providers/transporter_provider.dart';

class DriverAttendanceCalendarScreen extends StatefulWidget {
  const DriverAttendanceCalendarScreen({
    required this.driverId,
    required this.driverName,
    super.key,
  });

  final int driverId;
  final String driverName;

  @override
  State<DriverAttendanceCalendarScreen> createState() =>
      _DriverAttendanceCalendarScreenState();
}

class _DriverAttendanceCalendarScreenState
    extends State<DriverAttendanceCalendarScreen> {
  late DateTime _selectedMonth;

  @override
  void initState() {
    super.initState();
    _selectedMonth = DateTime(DateTime.now().year, DateTime.now().month, 1);
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadCalendar());
  }

  Future<void> _loadCalendar() {
    return context.read<TransporterProvider>().loadDriverAttendanceCalendar(
          driverId: widget.driverId,
          month: _selectedMonth.month,
          year: _selectedMonth.year,
        );
  }

  Future<void> _pickMonth() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedMonth,
      firstDate: DateTime(DateTime.now().year - 2),
      lastDate: DateTime(DateTime.now().year + 1, 12, 31),
      helpText: 'Select Month',
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _selectedMonth = DateTime(picked.year, picked.month, 1);
    });
    await _loadCalendar();
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'ON_DUTY':
      case 'PRESENT':
        return const Color(0xFF15803D);
      case 'NO_TRIP':
        return const Color(0xFF0F766E);
      case 'NO_DUTY':
        return const Color(0xFFD97706);
      case 'NOT_JOINED':
        return const Color(0xFF64748B);
      case 'LEAVE':
      case 'ABSENT':
        return const Color(0xFFB91C1C);
      default:
        return const Color(0xFF6B7280);
    }
  }

  String _monthName(int month) {
    const names = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    if (month < 1 || month > 12) {
      return month.toString();
    }
    return names[month - 1];
  }

  String _dateLabel(DateTime value) {
    final y = value.year.toString().padLeft(4, '0');
    final m = value.month.toString().padLeft(2, '0');
    final d = value.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.driverName} Attendance'),
        actions: [
          IconButton(
            onPressed: _pickMonth,
            icon: const Icon(Icons.calendar_month_outlined),
            tooltip: 'Select Month',
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
            final data = provider.driverAttendanceCalendar;
            if (provider.loading && data == null) {
              return const Center(child: CircularProgressIndicator());
            }
            if (provider.error != null && data == null) {
              return Center(child: Text(provider.error!));
            }
            if (data == null) {
              return const Center(child: Text('No attendance data'));
            }

            final days = data.days;
            final firstDay = DateTime(data.year, data.month, 1);
            final leadingEmpty = firstDay.weekday - 1;
            final trackedDays = days
                .where((day) => day.hasAttendance || day.hasMark)
                .toList()
              ..sort((a, b) => a.date.compareTo(b.date));
            final calendarCells = <Widget>[];
            for (var i = 0; i < leadingEmpty; i++) {
              calendarCells.add(const SizedBox.shrink());
            }
            for (final day in days) {
              final color = _statusColor(day.status);
              calendarCells.add(_DayTile(day: day, color: color));
            }

            return RefreshIndicator(
              onRefresh: _loadCalendar,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.date_range_outlined),
                      title: const Text('Month'),
                      subtitle: Text('${_monthName(data.month)} ${data.year}'),
                      trailing: TextButton(
                        onPressed: _pickMonth,
                        child: const Text('Change'),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Graphical Attendance Legend',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: const [
                              _LegendDot(
                                label: 'Present / On Duty',
                                color: Color(0xFF15803D),
                              ),
                              _LegendDot(
                                label: 'No Trip',
                                color: Color(0xFF0F766E),
                              ),
                              _LegendDot(
                                label: 'No Duty',
                                color: Color(0xFFD97706),
                              ),
                              _LegendDot(
                                label: 'Not Joined',
                                color: Color(0xFF64748B),
                              ),
                              _LegendDot(
                                label: 'Absent / Leave',
                                color: Color(0xFFB91C1C),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _SummaryChip(
                        label: 'Present',
                        value: data.totals.presentDays.toString(),
                        color: const Color(0xFF15803D),
                      ),
                      _SummaryChip(
                        label: 'Absent',
                        value: data.totals.absentDays.toString(),
                        color: const Color(0xFFB91C1C),
                      ),
                      _SummaryChip(
                        label: 'No Duty',
                        value: data.totals.noDutyDays.toString(),
                        color: const Color(0xFFD97706),
                      ),
                      _SummaryChip(
                        label: 'Effective Present',
                        value: data.totals.effectivePresentDays.toString(),
                        color: const Color(0xFF0A6B6F),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              'Tracked Days',
                              style: Theme.of(context).textTheme.bodyLarge,
                            ),
                          ),
                          Text(
                            trackedDays.length.toString(),
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  const _WeekHeader(),
                  const SizedBox(height: 8),
                  GridView.count(
                    crossAxisCount: 7,
                    crossAxisSpacing: 6,
                    mainAxisSpacing: 6,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    children: calendarCells,
                  ),
                  const SizedBox(height: 12),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Monthly Attendance Details',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 8),
                          if (trackedDays.isEmpty)
                            const Text('No marked attendance for this month.')
                          else
                            ...trackedDays.map((day) {
                              final color = _statusColor(day.status);
                              return Container(
                                margin: const EdgeInsets.only(bottom: 8),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 10,
                                  vertical: 8,
                                ),
                                decoration: BoxDecoration(
                                  color: color.withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(
                                    color: color.withValues(alpha: 0.35),
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        _dateLabel(day.date),
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                    Text(
                                      day.status,
                                      style: TextStyle(
                                        color: color,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            }),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _WeekHeader extends StatelessWidget {
  const _WeekHeader();

  @override
  Widget build(BuildContext context) {
    const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return Row(
      children: labels
          .map(
            (item) => Expanded(
              child: Center(
                child: Text(
                  item,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _SummaryChip extends StatelessWidget {
  const _SummaryChip({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '$label: $value',
        style: TextStyle(color: color, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _LegendDot extends StatelessWidget {
  const _LegendDot({
    required this.label,
    required this.color,
  });

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _DayTile extends StatelessWidget {
  const _DayTile({
    required this.day,
    required this.color,
  });

  final AttendanceCalendarDay day;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: [
        day.status,
        if (day.vehicleNumber != null) 'Vehicle: ${day.vehicleNumber}',
        if (day.serviceName != null) 'Service: ${day.serviceName}',
        if (day.startKm != null) 'Start KM: ${day.startKm}',
        if (day.endKm != null) 'End KM: ${day.endKm}',
      ].join('\n'),
      child: Container(
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Center(
          child: Text(
            day.date.day.toString(),
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
    );
  }
}
