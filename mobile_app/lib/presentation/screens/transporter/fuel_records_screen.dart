import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/vehicle.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class FuelRecordsScreen extends StatefulWidget {
  const FuelRecordsScreen({super.key});

  @override
  State<FuelRecordsScreen> createState() => _FuelRecordsScreenState();
}

class _FuelRecordsScreenState extends State<FuelRecordsScreen> {
  late DateTime _selectedMonth;

  @override
  void initState() {
    super.initState();
    _selectedMonth = DateTime(DateTime.now().year, DateTime.now().month, 1);
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadAll());
  }

  List<Vehicle> _vehiclesWithBalance(TransporterProvider provider) {
    final items = provider.vehicles
        .where(
          (vehicle) =>
              vehicle.fuelEstimatedLeftPercent != null &&
              vehicle.fuelEstimatedLeftLiters != null,
        )
        .toList()
      ..sort((a, b) {
        final aPercent = a.fuelEstimatedLeftPercent ?? 999;
        final bPercent = b.fuelEstimatedLeftPercent ?? 999;
        return aPercent.compareTo(bPercent);
      });
    return items;
  }

  Future<void> _loadAll({bool forceDashboard = false}) async {
    final provider = context.read<TransporterProvider>();
    await Future.wait([
      provider.loadDashboardData(
        force: forceDashboard,
        prefetchHeavyData: false,
      ),
      provider.loadFuelRecords(),
      provider.loadFuelMonthlySummary(
        month: _selectedMonth.month,
        year: _selectedMonth.year,
      ),
    ]);
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
    if (!mounted) {
      return;
    }
    await context.read<TransporterProvider>().loadFuelMonthlySummary(
          month: _selectedMonth.month,
          year: _selectedMonth.year,
        );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Fuel Records & Mileage'),
        actions: [
          IconButton(
            onPressed: _pickMonth,
            icon: const Icon(Icons.calendar_month_outlined),
            tooltip: 'Select month',
          ),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE7F1F0), Color(0xFFF8EFE6)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            final summary = provider.fuelMonthlySummary;

            if (provider.loading &&
                provider.fuelRecords.isEmpty &&
                summary == null) {
              return const Center(child: CircularProgressIndicator());
            }

            if (provider.error != null &&
                provider.fuelRecords.isEmpty &&
                summary == null) {
              return Center(child: Text(provider.error!));
            }

            return RefreshIndicator(
              onRefresh: () => _loadAll(forceDashboard: true),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                children: [
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.date_range_outlined),
                      title: const Text('Monthly Fuel Analytics'),
                      subtitle: Text(
                        'Month: ${_selectedMonth.month}/${_selectedMonth.year}\n'
                        'Mileage uses consecutive odometer fuel readings (full-to-full logic).',
                      ),
                      trailing: TextButton(
                        onPressed: _pickMonth,
                        child: const Text('Change'),
                      ),
                    ),
                  ),
                  if (_vehiclesWithBalance(provider).isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Current Tank Balance',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                    const SizedBox(height: 6),
                    ..._vehiclesWithBalance(provider).asMap().entries.map((entry) {
                      final index = entry.key;
                      final vehicle = entry.value;
                      final percentLeft = vehicle.fuelEstimatedLeftPercent ?? 0;
                      final indicatorColor = percentLeft <= 10
                          ? const Color(0xFFC84747)
                          : percentLeft <= 30
                              ? const Color(0xFFE2A93B)
                              : percentLeft <= 50
                                  ? const Color(0xFF3E94B8)
                                  : const Color(0xFF0A8F6A);
                      return StaggeredEntrance(
                        delay: Duration(milliseconds: 35 * index),
                        child: Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    const Icon(Icons.local_shipping_outlined),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        vehicle.vehicleNumber,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                              fontWeight: FontWeight.w700,
                                            ),
                                      ),
                                    ),
                                    Text(
                                      '${vehicle.fuelEstimatedLeftLiters!.toStringAsFixed(2)} L',
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleSmall
                                          ?.copyWith(
                                            fontWeight: FontWeight.w700,
                                          ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(999),
                                  child: LinearProgressIndicator(
                                    minHeight: 12,
                                    value: (percentLeft / 100).clamp(0, 1),
                                    backgroundColor: const Color(0xFFE8E8E8),
                                    valueColor: AlwaysStoppedAnimation<Color>(
                                      indicatorColor,
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    _InfoChip(
                                      label: '% Left',
                                      value: '${percentLeft.toStringAsFixed(2)}%',
                                    ),
                                    if (vehicle.fuelEstimatedTankCapacityLiters !=
                                        null)
                                      _InfoChip(
                                        label: 'Tank',
                                        value:
                                            '${vehicle.fuelEstimatedTankCapacityLiters!.toStringAsFixed(2)} L',
                                      ),
                                    if (vehicle.fuelAverageMileage != null)
                                      _InfoChip(
                                        label: 'Avg Mileage',
                                        value:
                                            '${vehicle.fuelAverageMileage!.toStringAsFixed(2)} km/l',
                                      ),
                                    if (vehicle.fuelEstimatedKmLeft != null)
                                      _InfoChip(
                                        label: 'KM Left',
                                        value:
                                            '${vehicle.fuelEstimatedKmLeft} km',
                                      ),
                                    if (vehicle.latestOdometerKm != null)
                                      _InfoChip(
                                        label: 'Latest Odo',
                                        value:
                                            '${vehicle.latestOdometerKm} km',
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
                  if (summary != null) ...[
                    const SizedBox(height: 8),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            _InfoChip(
                              label: 'Vehicles Filled',
                              value: summary.totalVehiclesFilled.toString(),
                            ),
                            _InfoChip(
                              label: 'Fuel Fills',
                              value: summary.totalFuelFills.toString(),
                            ),
                            _InfoChip(
                              label: 'Total Liters',
                              value: summary.totalLiters.toStringAsFixed(2),
                            ),
                            _InfoChip(
                              label: 'Total Amount',
                              value: summary.totalAmount.toStringAsFixed(2),
                            ),
                            _InfoChip(
                              label: 'Avg Mileage',
                              value:
                                  '${summary.overallAverageMileage.toStringAsFixed(2)} km/l',
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    ...summary.rows.asMap().entries.map((entry) {
                      final index = entry.key;
                      final row = entry.value;
                      return StaggeredEntrance(
                        delay: Duration(milliseconds: 45 * index),
                        child: Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            leading: const Icon(Icons.local_shipping_outlined),
                            title: Text(row.vehicleNumber),
                            subtitle: Text(
                              'Fills: ${row.fuelFillCount} | Liters: ${row.totalLiters.toStringAsFixed(2)}\n'
                              'Amount: ${row.totalAmount.toStringAsFixed(2)} | KM: ${row.totalKm}\n'
                              'Avg Mileage: ${row.averageMileage.toStringAsFixed(2)} km/l',
                            ),
                          ),
                        ),
                      );
                    }),
                  ],
                  const SizedBox(height: 10),
                  Text(
                    'All Fuel Logs',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 6),
                  if (provider.fuelRecords.isEmpty)
                    const _EmptyState(
                      icon: Icons.local_gas_station_outlined,
                      message: 'No fuel records available yet.',
                    )
                  else
                    ...provider.fuelRecords.asMap().entries.map((entry) {
                      final index = entry.key;
                      final fuel = entry.value;
                      return StaggeredEntrance(
                        delay: Duration(milliseconds: 40 * index),
                        child: Card(
                          margin: const EdgeInsets.only(bottom: 10),
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      width: 42,
                                      height: 42,
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFCF6E41)
                                            .withValues(alpha: 0.18),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: const Icon(
                                        Icons.local_gas_station_rounded,
                                        color: Color(0xFFCF6E41),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Text(
                                        '${fuel.vehicleNumber} - ${fuel.driverName}',
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                                fontWeight: FontWeight.w700),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Wrap(
                                  spacing: 10,
                                  runSpacing: 8,
                                  children: [
                                    _InfoChip(
                                      label: 'Type',
                                      value: fuel.isTowerDiesel
                                          ? 'Tower Diesel'
                                          : 'Vehicle Fuel',
                                    ),
                                    if (fuel.isTowerDiesel) ...[
                                      _InfoChip(
                                        label: 'Fuel',
                                        value:
                                            '${fuel.fuelFilled.toStringAsFixed(2)} L',
                                      ),
                                      _InfoChip(
                                        label: 'Run',
                                        value: '${fuel.runKm} KM',
                                      ),
                                      if (fuel.siteName.isNotEmpty)
                                        _InfoChip(
                                          label: 'Site',
                                          value: fuel.siteName,
                                        ),
                                    ] else ...[
                                      _InfoChip(
                                        label: 'Liters',
                                        value:
                                            '${fuel.liters.toStringAsFixed(2)} L',
                                      ),
                                      _InfoChip(
                                        label: 'Amount',
                                        value: fuel.amount.toStringAsFixed(2),
                                      ),
                                      if (fuel.odometerKm != null)
                                        _InfoChip(
                                          label: 'Odo',
                                          value: '${fuel.odometerKm} KM',
                                        ),
                                    ],
                                    _InfoChip(
                                      label: 'Date',
                                      value: fuel.effectiveDate
                                          .toLocal()
                                          .toString()
                                          .split(' ')
                                          .first,
                                    ),
                                  ],
                                ),
                                if (fuel.isTowerDiesel &&
                                    fuel.logbookPhotoUrl.isNotEmpty)
                                  Align(
                                    alignment: Alignment.centerLeft,
                                    child: TextButton.icon(
                                      onPressed: () => _openPhoto(
                                        context,
                                        fuel.logbookPhotoUrl,
                                        title:
                                            '${fuel.vehicleNumber} - ${fuel.siteName.isEmpty ? 'Tower Diesel' : fuel.siteName}',
                                      ),
                                      icon: const Icon(Icons.photo_outlined),
                                      label: const Text('View Logbook Photo'),
                                    ),
                                  )
                                else if (!fuel.isTowerDiesel &&
                                    (fuel.meterImageUrl.isNotEmpty ||
                                        fuel.billImageUrl.isNotEmpty))
                                  Padding(
                                    padding: const EdgeInsets.only(top: 4),
                                    child: Wrap(
                                      spacing: 8,
                                      runSpacing: 4,
                                      children: [
                                        if (fuel.meterImageUrl.isNotEmpty)
                                          TextButton.icon(
                                            onPressed: () => _openPhoto(
                                              context,
                                              fuel.meterImageUrl,
                                              title:
                                                  '${fuel.vehicleNumber} - Odometer Photo',
                                            ),
                                            icon: const Icon(
                                              Icons.speed_outlined,
                                            ),
                                            label: const Text(
                                              'View Odometer Photo',
                                            ),
                                          ),
                                        if (fuel.billImageUrl.isNotEmpty)
                                          TextButton.icon(
                                            onPressed: () => _openPhoto(
                                              context,
                                              fuel.billImageUrl,
                                              title:
                                                  '${fuel.vehicleNumber} - Slip Photo',
                                            ),
                                            icon: const Icon(
                                              Icons.receipt_long_outlined,
                                            ),
                                            label: const Text(
                                              'View Slip Photo',
                                            ),
                                          ),
                                      ],
                                    ),
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

  void _openPhoto(
    BuildContext context,
    String imageUrl, {
    required String title,
  }) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Dialog(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420, maxHeight: 620),
            child: Column(
              children: [
                ListTile(
                  title: Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  trailing: IconButton(
                    onPressed: () => Navigator.of(dialogContext).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ),
                const Divider(height: 1),
                Expanded(
                  child: InteractiveViewer(
                    child: Image.network(
                      imageUrl,
                      fit: BoxFit.contain,
                      errorBuilder: (_, __, ___) {
                        return const Center(
                          child: Padding(
                            padding: EdgeInsets.all(24),
                            child: Text('Unable to load image.'),
                          ),
                        );
                      },
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F3EE),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        '$label: $value',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Colors.black.withValues(alpha: 0.72),
            ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 52, color: Colors.black.withValues(alpha: 0.4)),
            const SizedBox(height: 10),
            Text(
              message,
              style: Theme.of(context).textTheme.bodyLarge,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
