import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/attendance_calendar.dart';
import '../../providers/transporter_provider.dart';

class AttendanceMarkingCalendarScreen extends StatefulWidget {
  const AttendanceMarkingCalendarScreen({super.key});

  @override
  State<AttendanceMarkingCalendarScreen> createState() =>
      _AttendanceMarkingCalendarScreenState();
}

class _AttendanceMarkingCalendarScreenState
    extends State<AttendanceMarkingCalendarScreen> {
  late DateTime _selectedMonth;
  int? _selectedDriverId;

  @override
  void initState() {
    super.initState();
    _selectedMonth = DateTime(DateTime.now().year, DateTime.now().month, 1);
    WidgetsBinding.instance.addPostFrameCallback((_) => _initialize());
  }

  Future<void> _initialize() async {
    final provider = context.read<TransporterProvider>();
    await provider.loadDailyAttendance(date: DateTime.now());
    if (!mounted) {
      return;
    }
    if (_selectedDriverId == null && provider.dailyAttendance.isNotEmpty) {
      _selectedDriverId = provider.dailyAttendance.first.driverId;
    }
    await _loadCalendar();
  }

  Future<void> _loadCalendar() async {
    final driverId = _selectedDriverId;
    if (driverId == null) {
      return;
    }
    await context.read<TransporterProvider>().loadDriverAttendanceCalendar(
          driverId: driverId,
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

  Future<void> _markStatusForDay(AttendanceCalendarDay day) async {
    final driverId = _selectedDriverId;
    if (driverId == null) {
      return;
    }
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final dayDate = DateTime(day.date.year, day.date.month, day.date.day);
    if (day.status == 'NOT_JOINED') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('This date is before the driver joined this transporter.'),
        ),
      );
      return;
    }
    if (dayDate.isAfter(today)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cannot mark future date attendance.')),
      );
      return;
    }

    final status = await _showStatusPicker();
    if (status == null || !mounted) {
      return;
    }
    final success =
        await context.read<TransporterProvider>().markDriverAttendance(
              driverId: driverId,
              status: status,
              date: day.date,
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
      SnackBar(content: Text('Marked $status for ${_dateLabel(day.date)}')),
    );
    await _loadCalendar();
  }

  Future<String?> _showStatusPicker() {
    return showModalBottomSheet<String>(
      context: context,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Mark Attendance',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                const Text('Choose status for selected date'),
                const SizedBox(height: 14),
                _StatusButton(
                  label: 'Present',
                  status: 'PRESENT',
                  color: const Color(0xFF15803D),
                ),
                const SizedBox(height: 8),
                _StatusButton(
                  label: 'Absent',
                  status: 'ABSENT',
                  color: const Color(0xFFB91C1C),
                ),
                const SizedBox(height: 8),
                _StatusButton(
                  label: 'Leave',
                  status: 'LEAVE',
                  color: const Color(0xFFD97706),
                ),
              ],
            ),
          ),
        );
      },
    );
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

  Color _statusColor(String status) {
    switch (status) {
      case 'ON_DUTY':
      case 'PRESENT':
        return const Color(0xFF15803D);
      case 'NO_TRIP':
        return const Color(0xFF0F766E);
      case 'NO_DUTY':
        return const Color(0xFF0A6B6F);
      case 'NOT_JOINED':
        return const Color(0xFF64748B);
      case 'LEAVE':
        return const Color(0xFFD97706);
      case 'ABSENT':
        return const Color(0xFFB91C1C);
      default:
        return const Color(0xFF6B7280);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mark Attendance Calendar'),
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
            final drivers = provider.dailyAttendance
                .map((item) => (id: item.driverId, name: item.driverName))
                .toList()
              ..sort((a, b) =>
                  a.name.toLowerCase().compareTo(b.name.toLowerCase()));

            final selectedDriverId = _selectedDriverId ??
                (drivers.isEmpty ? null : drivers.first.id);

            final calendar = provider.driverAttendanceCalendar;
            final isSelectedDriverCalendar = calendar != null &&
                selectedDriverId != null &&
                calendar.driverId == selectedDriverId &&
                calendar.month == _selectedMonth.month &&
                calendar.year == _selectedMonth.year;

            if (provider.loading && drivers.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            return RefreshIndicator(
              onRefresh: _initialize,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Select Driver',
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 8),
                          DropdownButtonFormField<int>(
                            key: ValueKey<int?>(selectedDriverId),
                            initialValue: selectedDriverId,
                            decoration: const InputDecoration(
                              labelText: 'Driver',
                              prefixIcon: Icon(Icons.badge_outlined),
                            ),
                            items: drivers
                                .map(
                                  (driver) => DropdownMenuItem<int>(
                                    value: driver.id,
                                    child: Text(driver.name),
                                  ),
                                )
                                .toList(),
                            onChanged: drivers.isEmpty
                                ? null
                                : (value) async {
                                    if (value == null) {
                                      return;
                                    }
                                    setState(() {
                                      _selectedDriverId = value;
                                    });
                                    await _loadCalendar();
                                  },
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.date_range_outlined),
                      title: const Text('Month'),
                      subtitle: Text(
                          '${_monthName(_selectedMonth.month)} ${_selectedMonth.year}'),
                      trailing: TextButton(
                        onPressed: _pickMonth,
                        child: const Text('Change'),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(12),
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
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
                            color: Color(0xFF0A6B6F),
                          ),
                          _LegendDot(
                            label: 'Leave',
                            color: Color(0xFFD97706),
                          ),
                          _LegendDot(
                            label: 'Absent',
                            color: Color(0xFFB91C1C),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (provider.loading && !isSelectedDriverCalendar)
                    const Padding(
                      padding: EdgeInsets.only(top: 40),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (selectedDriverId == null)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('No drivers available.'),
                      ),
                    )
                  else if (calendar == null || !isSelectedDriverCalendar)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('Unable to load calendar data.'),
                      ),
                    )
                  else ...[
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _SummaryChip(
                          label: 'Present',
                          value: calendar.totals.presentDays.toString(),
                          color: const Color(0xFF15803D),
                        ),
                        _SummaryChip(
                          label: 'Absent',
                          value: calendar.totals.absentDays.toString(),
                          color: const Color(0xFFB91C1C),
                        ),
                        _SummaryChip(
                          label: 'No Duty',
                          value: calendar.totals.noDutyDays.toString(),
                          color: const Color(0xFF0A6B6F),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    const _WeekHeader(),
                    const SizedBox(height: 8),
                    GridView.count(
                      crossAxisCount: 7,
                      crossAxisSpacing: 6,
                      mainAxisSpacing: 6,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      children: _buildCalendarCells(calendar.days),
                    ),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  List<Widget> _buildCalendarCells(List<AttendanceCalendarDay> days) {
    if (days.isEmpty) {
      return const <Widget>[];
    }
    final firstDay = DateTime(days.first.date.year, days.first.date.month, 1);
    final leadingEmpty = firstDay.weekday - 1;
    final cells = <Widget>[];
    for (var i = 0; i < leadingEmpty; i++) {
      cells.add(const SizedBox.shrink());
    }
    for (final day in days) {
      final color = _statusColor(day.status);
      cells.add(
        _MarkableDayTile(
          day: day,
          color: color,
          onTap: () => _markStatusForDay(day),
        ),
      );
    }
    return cells;
  }
}

class _MarkableDayTile extends StatelessWidget {
  const _MarkableDayTile({
    required this.day,
    required this.color,
    required this.onTap,
  });

  final AttendanceCalendarDay day;
  final Color color;
  final VoidCallback onTap;

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
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
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
        ),
      ),
    );
  }
}

class _StatusButton extends StatelessWidget {
  const _StatusButton({
    required this.label,
    required this.status,
    required this.color,
  });

  final String label;
  final String status;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return FilledButton.tonalIcon(
      onPressed: () => Navigator.of(context).pop(status),
      style: FilledButton.styleFrom(
        foregroundColor: color,
        backgroundColor: color.withValues(alpha: 0.14),
      ),
      icon: const Icon(Icons.check_circle_outline),
      label: Text(label),
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
