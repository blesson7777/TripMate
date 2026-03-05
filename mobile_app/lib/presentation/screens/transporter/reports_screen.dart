import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  final _monthController = TextEditingController();
  final _yearController = TextEditingController();
  final _vehicleController = TextEditingController();

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _monthController.text = now.month.toString();
    _yearController.text = now.year.toString();
  }

  @override
  void dispose() {
    _monthController.dispose();
    _yearController.dispose();
    _vehicleController.dispose();
    super.dispose();
  }

  Future<void> _loadReport() async {
    final month = int.tryParse(_monthController.text.trim());
    final year = int.tryParse(_yearController.text.trim());

    if (month == null || year == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Month and year must be valid numbers.')),
      );
      return;
    }

    await context.read<TransporterProvider>().loadMonthlyReport(
          month: month,
          year: year,
          vehicleId: int.tryParse(_vehicleController.text.trim()),
        );
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Monthly Trip Sheet')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFEAF3F2), Color(0xFFF8EFE4)],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Consumer<TransporterProvider>(
            builder: (context, provider, _) {
              final report = provider.monthlyReport;
              return Column(
                children: [
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: TextField(
                                    controller: _monthController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'Month',
                                      prefixIcon:
                                          Icon(Icons.calendar_today_outlined),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: TextField(
                                    controller: _yearController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'Year',
                                      prefixIcon:
                                          Icon(Icons.date_range_outlined),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            TextField(
                              controller: _vehicleController,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(
                                labelText: 'Vehicle ID (optional)',
                                prefixIcon: Icon(Icons.local_shipping_outlined),
                              ),
                            ),
                            const SizedBox(height: 10),
                            Container(
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(16),
                                gradient: const LinearGradient(
                                  colors: [
                                    Color(0xFF0A6B6F),
                                    Color(0xFF198288),
                                  ],
                                ),
                              ),
                              child: FilledButton.icon(
                                onPressed:
                                    provider.loading ? null : _loadReport,
                                style: FilledButton.styleFrom(
                                  backgroundColor: Colors.transparent,
                                  shadowColor: Colors.transparent,
                                ),
                                icon: provider.loading
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.white,
                                        ),
                                      )
                                    : const Icon(Icons.analytics_outlined),
                                label: Text(provider.loading
                                    ? 'Generating...'
                                    : 'Generate Report'),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (provider.error != null)
                    Text(provider.error!,
                        style: TextStyle(color: colors.error)),
                  if (report != null) ...[
                    StaggeredEntrance(
                      delay: const Duration(milliseconds: 200),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 12,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: _ReportSummaryChip(
                                  icon: Icons.event_note_outlined,
                                  label: 'Total Days',
                                  value: '${report.totalDays}',
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: _ReportSummaryChip(
                                  icon: Icons.speed_outlined,
                                  label: 'Total KM',
                                  value: '${report.totalKm}',
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Expanded(
                      child: ListView.builder(
                        itemCount: report.rows.length,
                        itemBuilder: (context, index) {
                          final row = report.rows[index];
                          return StaggeredEntrance(
                            delay: Duration(milliseconds: 45 * index),
                            child: Card(
                              margin: const EdgeInsets.only(bottom: 8),
                              child: ListTile(
                                leading: Container(
                                  width: 36,
                                  height: 36,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0A6B6F)
                                        .withValues(alpha: 0.14),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: const Icon(
                                    Icons.calendar_month_outlined,
                                    size: 20,
                                    color: Color(0xFF0A6B6F),
                                  ),
                                ),
                                title: Text(row.date
                                    .toLocal()
                                    .toString()
                                    .split(' ')
                                    .first),
                                subtitle: Text(
                                  'Start: ${row.startKm} | End: ${row.endKm} | Total: ${row.totalKm}',
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ReportSummaryChip extends StatelessWidget {
  const _ReportSummaryChip({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFF2F8F7),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        child: Row(
          children: [
            Icon(icon, size: 20, color: const Color(0xFF0A6B6F)),
            const SizedBox(width: 6),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    value,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  Text(
                    label,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.black.withValues(alpha: 0.65),
                        ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
