import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';

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
    return Scaffold(
      appBar: AppBar(title: const Text('Monthly Trip Sheet')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            final report = provider.monthlyReport;
            return Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _monthController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Month'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _yearController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Year'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _vehicleController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Vehicle ID (optional)',
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: provider.loading ? null : _loadReport,
                    child: provider.loading
                        ? const CircularProgressIndicator()
                        : const Text('Generate Report'),
                  ),
                ),
                const SizedBox(height: 16),
                if (provider.error != null)
                  Text(provider.error!, style: const TextStyle(color: Colors.red)),
                if (report != null) ...[
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Total Days: ${report.totalDays} | Total KM: ${report.totalKm}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView.builder(
                      itemCount: report.rows.length,
                      itemBuilder: (context, index) {
                        final row = report.rows[index];
                        return Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            title: Text(row.date.toLocal().toString().split(' ').first),
                            subtitle: Text(
                              'Start KM: ${row.startKm} | End KM: ${row.endKm} | Total KM: ${row.totalKm}',
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
    );
  }
}
