import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/salary_advance.dart';
import '../../../domain/entities/salary_summary.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'driver_allocation_screen.dart';

class DriversScreen extends StatefulWidget {
  const DriversScreen({super.key});

  @override
  State<DriversScreen> createState() => _DriversScreenState();
}

class _DriversScreenState extends State<DriversScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadDashboardData();
    });
  }

  void _openAllocationPage() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const DriverAllocationScreen()),
    );
  }

  Future<void> _confirmRemoveDriver({
    required int driverId,
    required String driverName,
  }) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Remove Driver'),
          content: Text(
            'Remove $driverName from this transporter? '
            'This will clear the current transporter allocation, vehicle, and default service.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Remove'),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) {
      return;
    }

    final success = await context
        .read<TransporterProvider>()
        .removeDriverFromTransporter(driverId: driverId);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          success
              ? '$driverName removed from transporter.'
              : (context.read<TransporterProvider>().error ??
                  'Unable to remove driver.'),
        ),
      ),
    );
  }

  Future<void> _openVehicleAllocationSheet() async {
    final provider = context.read<TransporterProvider>();
    final drivers = provider.drivers;
    final vehicles = provider.vehicles;
    final services = provider.services.where((item) => item.isActive).toList();

    if (drivers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No drivers available for vehicle allocation')),
      );
      return;
    }

    int selectedDriverId = drivers.first.id;
    int? selectedVehicleId = drivers.first.vehicleId;
    int? selectedServiceId = drivers.first.defaultServiceId;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
          child: StatefulBuilder(
            builder: (context, setSheetState) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Vehicle Allocation',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Select driver and set default vehicle/service.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.black.withValues(alpha: 0.68),
                        ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<int>(
                    initialValue: selectedDriverId,
                    decoration: const InputDecoration(
                      labelText: 'Driver',
                      prefixIcon: Icon(Icons.person_outline_rounded),
                    ),
                    items: drivers
                        .map(
                          (driver) => DropdownMenuItem<int>(
                            value: driver.id,
                            child: Text(driver.username),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      final selectedDriver = drivers.firstWhere(
                        (driver) => driver.id == value,
                      );
                      setSheetState(() {
                        selectedDriverId = value;
                        selectedVehicleId = selectedDriver.vehicleId;
                        selectedServiceId = selectedDriver.defaultServiceId;
                      });
                    },
                  ),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<int?>(
                    initialValue: selectedVehicleId,
                    decoration: const InputDecoration(
                      labelText: 'Vehicle',
                      prefixIcon: Icon(Icons.local_shipping_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('Unassign vehicle'),
                      ),
                      ...vehicles.map(
                        (vehicle) => DropdownMenuItem<int?>(
                          value: vehicle.id,
                          child: Text('${vehicle.vehicleNumber} - ${vehicle.model}'),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      setSheetState(() {
                        selectedVehicleId = value;
                      });
                    },
                  ),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<int?>(
                    initialValue: selectedServiceId,
                    decoration: const InputDecoration(
                      labelText: 'Default Service',
                      prefixIcon: Icon(Icons.miscellaneous_services_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('Clear default service'),
                      ),
                      ...services.map(
                        (service) => DropdownMenuItem<int?>(
                          value: service.id,
                          child: Text(service.name),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      setSheetState(() {
                        selectedServiceId = value;
                      });
                    },
                  ),
                  const SizedBox(height: 14),
                  Consumer<TransporterProvider>(
                    builder: (context, transporterProvider, _) {
                      return FilledButton.icon(
                        onPressed: transporterProvider.loading
                            ? null
                            : () async {
                                final success = await context
                                    .read<TransporterProvider>()
                                    .assignVehicleToDriver(
                                      driverId: selectedDriverId,
                                      vehicleId: selectedVehicleId,
                                      serviceId: selectedServiceId,
                                    );
                                if (!context.mounted) {
                                  return;
                                }
                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context.read<TransporterProvider>().error ??
                                            'Unable to update vehicle allocation',
                                      ),
                                    ),
                                  );
                                  return;
                                }
                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Vehicle allocation updated'),
                                  ),
                                );
                              },
                        icon: transporterProvider.loading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.save_outlined),
                        label: const Text('Save'),
                      );
                    },
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  Future<void> _openAssignVehicleSheet({
    required int driverId,
    required int? selectedVehicleId,
    required int? selectedServiceId,
  }) async {
    final vehicles = context.read<TransporterProvider>().vehicles;
    final services = context
        .read<TransporterProvider>()
        .services
        .where((item) => item.isActive)
        .toList();
    int? selectedId = selectedVehicleId;
    int? selectedService = selectedServiceId;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
          child: StatefulBuilder(
            builder: (context, setSheetState) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Allocate Vehicle',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Choose default vehicle and service for this driver.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.black.withValues(alpha: 0.68),
                        ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<int?>(
                    initialValue: selectedId,
                    decoration: const InputDecoration(
                      labelText: 'Vehicle',
                      prefixIcon: Icon(Icons.local_shipping_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('Unassign vehicle'),
                      ),
                      ...vehicles.map(
                        (vehicle) => DropdownMenuItem<int?>(
                          value: vehicle.id,
                          child: Text('${vehicle.vehicleNumber} - ${vehicle.model}'),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      setSheetState(() {
                        selectedId = value;
                      });
                    },
                  ),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<int?>(
                    initialValue: selectedService,
                    decoration: const InputDecoration(
                      labelText: 'Default Service',
                      prefixIcon: Icon(Icons.miscellaneous_services_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('Clear default service'),
                      ),
                      ...services.map(
                        (service) => DropdownMenuItem<int?>(
                          value: service.id,
                          child: Text(service.name),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      setSheetState(() {
                        selectedService = value;
                      });
                    },
                  ),
                  const SizedBox(height: 14),
                  Consumer<TransporterProvider>(
                    builder: (context, provider, _) {
                      return FilledButton.icon(
                        onPressed: provider.loading
                            ? null
                            : () async {
                                final success = await context
                                    .read<TransporterProvider>()
                                    .assignVehicleToDriver(
                                      driverId: driverId,
                                      vehicleId: selectedId,
                                      serviceId: selectedService,
                                    );
                                if (!context.mounted) {
                                  return;
                                }
                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context.read<TransporterProvider>().error ??
                                            'Unable to update vehicle allocation',
                                      ),
                                    ),
                                  );
                                  return;
                                }
                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Vehicle allocation updated'),
                                  ),
                                );
                              },
                        icon: provider.loading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.save_outlined),
                        label: const Text('Save'),
                      );
                    },
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Drivers'),
        actions: [
          IconButton(
            onPressed: _openVehicleAllocationSheet,
            icon: const Icon(Icons.directions_car_filled_outlined),
            tooltip: 'Vehicle Allocation',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAllocationPage,
        icon: const Icon(Icons.person_add_alt_1_rounded),
        label: const Text('Allocate Driver'),
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
            if (provider.loading && provider.drivers.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (provider.error != null && provider.drivers.isEmpty) {
              return Center(child: Text(provider.error!));
            }

            if (provider.drivers.isEmpty) {
              return const _EmptyState(
                icon: Icons.badge_outlined,
                message: 'No drivers are assigned yet.',
              );
            }

            return RefreshIndicator(
              onRefresh: () => provider.loadDashboardData(force: true),
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                itemCount: provider.drivers.length,
                itemBuilder: (context, index) {
                  final driver = provider.drivers[index];
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
                                Container(
                                  width: 46,
                                  height: 46,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF228B8D)
                                        .withValues(alpha: 0.14),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: const Icon(
                                    Icons.person_outline_rounded,
                                    color: Color(0xFF228B8D),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        driver.username,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                              fontWeight: FontWeight.w700,
                                            ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        'License: ${driver.licenseNumber}',
                                        style:
                                            Theme.of(context).textTheme.bodySmall,
                                      ),
                                      Text(
                                        'Vehicle: ${driver.vehicleNumber ?? "Not assigned"}',
                                        style:
                                            Theme.of(context).textTheme.bodySmall,
                                      ),
                                      Text(
                                        'Default Service: ${driver.defaultServiceName ?? "Not set"}',
                                        style:
                                            Theme.of(context).textTheme.bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Align(
                              alignment: Alignment.centerRight,
                              child: Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                alignment: WrapAlignment.end,
                                children: [
                                  OutlinedButton.icon(
                                    onPressed: () => _openAssignVehicleSheet(
                                      driverId: driver.id,
                                      selectedVehicleId: driver.vehicleId,
                                      selectedServiceId: driver.defaultServiceId,
                                    ),
                                    icon: const Icon(Icons.directions_car_filled_outlined),
                                    label: const Text('Allocate Vehicle'),
                                  ),
                                  OutlinedButton.icon(
                                    onPressed: provider.loading
                                        ? null
                                        : () => _confirmRemoveDriver(
                                              driverId: driver.id,
                                              driverName: driver.username,
                                            ),
                                    icon: const Icon(Icons.person_remove_outlined),
                                    label: const Text('Remove Driver'),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            );
          },
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


class SalaryScreen extends StatefulWidget {
  const SalaryScreen({super.key});

  @override
  State<SalaryScreen> createState() => _SalaryScreenState();
}

class _SalaryScreenState extends State<SalaryScreen> {
  late DateTime _selectedMonth;
  bool _showPaidRows = false;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _selectedMonth = DateTime(now.year, now.month, 1);
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadAll());
  }

  Future<void> _loadAll({bool forceDashboard = false}) async {
    final provider = context.read<TransporterProvider>();
    await Future.wait([
      provider.loadDashboardData(force: forceDashboard, prefetchHeavyData: false),
      provider.loadSalaryMonthlySummary(month: _selectedMonth.month, year: _selectedMonth.year),
    ]);
  }

  String _monthLabel(DateTime value) {
    const names = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    return '${names[value.month]} ${value.year}';
  }

  String _dateLabel(DateTime value) => '${value.day.toString().padLeft(2, '0')}-${value.month.toString().padLeft(2, '0')}-${value.year}';
  String _money(num value) => 'Rs. ${value.toStringAsFixed(2)}';

  Future<void> _pickMonth() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedMonth,
      firstDate: DateTime(DateTime.now().year - 3, 1, 1),
      lastDate: DateTime(DateTime.now().year + 1, 12, 31),
      helpText: 'Select Salary Month',
    );
    if (picked == null) return;
    setState(() => _selectedMonth = DateTime(picked.year, picked.month, 1));
    if (!mounted) return;
    await context.read<TransporterProvider>().loadSalaryMonthlySummary(month: _selectedMonth.month, year: _selectedMonth.year);
  }

  Future<void> _shiftMonth(int delta) async {
    setState(() => _selectedMonth = DateTime(_selectedMonth.year, _selectedMonth.month + delta, 1));
    await context.read<TransporterProvider>().loadSalaryMonthlySummary(month: _selectedMonth.month, year: _selectedMonth.year);
  }

  Future<void> _openPreviousMonth() async {
    final previousMonth = DateTime(_selectedMonth.year, _selectedMonth.month - 1, 1);
    setState(() {
      _selectedMonth = previousMonth;
    });
    await context.read<TransporterProvider>().loadSalaryMonthlySummary(
          month: _selectedMonth.month,
          year: _selectedMonth.year,
        );
  }

  Future<void> _openSalarySheet(DriverSalarySummary row) async {
    final formKey = GlobalKey<FormState>();
    final salaryController = TextEditingController(
      text: row.monthlySalary > 0 ? row.monthlySalary.toStringAsFixed(2) : '',
    );
    final clController = TextEditingController(text: row.clCount > 0 ? row.clCount.toString() : '');
    final notesController = TextEditingController(text: row.notes);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.of(sheetContext).viewInsets.bottom),
          child: FractionallySizedBox(
            heightFactor: 0.9,
            child: Container(
              decoration: const BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
              ),
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 18),
              child: Form(
                key: formKey,
                child: Consumer<TransporterProvider>(
                  builder: (context, provider, _) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: SingleChildScrollView(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  row.driverName,
                                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                        fontWeight: FontWeight.w700,
                                      ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  'Net payable: ${_money(row.netPayableAmount)} | Due: ${_dateLabel(row.salaryDueDate)}',
                                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                        color: Colors.black54,
                                      ),
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: salaryController,
                                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                  decoration: const InputDecoration(
                                    labelText: 'Monthly Salary',
                                    prefixIcon: Icon(Icons.currency_rupee_rounded),
                                  ),
                                  validator: (value) {
                                    final parsed = double.tryParse((value ?? '').trim());
                                    if (parsed == null || parsed <= 0) {
                                      return 'Enter a valid monthly salary';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 10),
                                TextFormField(
                                  controller: clController,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(
                                    labelText: 'CL Count (optional)',
                                    prefixIcon: Icon(Icons.event_available_outlined),
                                  ),
                                  validator: (value) {
                                    if (value == null || value.trim().isEmpty) return null;
                                    final parsed = int.tryParse(value.trim());
                                    if (parsed == null || parsed < 0) {
                                      return 'Enter valid CL count';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 10),
                                TextFormField(
                                  controller: notesController,
                                  maxLines: 2,
                                  decoration: const InputDecoration(
                                    labelText: 'Notes (optional)',
                                    prefixIcon: Icon(Icons.sticky_note_2_outlined),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 14),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: provider.loading
                                    ? null
                                    : () async {
                                        if (!formKey.currentState!.validate()) return;
                                        final messenger = ScaffoldMessenger.of(context);
                                        final transporterProvider = context.read<TransporterProvider>();
                                        final success = await transporterProvider.updateDriverMonthlySalary(
                                          driverId: row.driverId,
                                          monthlySalary: double.parse(salaryController.text.trim()),
                                          refreshMonth: row.month,
                                          refreshYear: row.year,
                                        );
                                        if (!mounted) return;
                                        if (!success) {
                                          messenger.showSnackBar(
                                            SnackBar(
                                              content: Text(
                                                transporterProvider.error ?? 'Unable to update salary.',
                                              ),
                                            ),
                                          );
                                          return;
                                        }
                                        messenger.showSnackBar(
                                          const SnackBar(
                                            content: Text('Monthly salary updated.'),
                                          ),
                                        );
                                      },
                                icon: provider.loading
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(strokeWidth: 2),
                                      )
                                    : const Icon(Icons.save_outlined),
                                label: const Text('Save'),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: FilledButton.icon(
                                onPressed: provider.loading || row.isPaid || !row.canPay
                                    ? null
                                    : () async {
                                        if (!formKey.currentState!.validate()) return;
                                        final clText = clController.text.trim();
                                        final messenger = ScaffoldMessenger.of(context);
                                        final navigator = Navigator.of(sheetContext);
                                        final transporterProvider = context.read<TransporterProvider>();
                                        final success = await transporterProvider.payDriverSalary(
                                          driverId: row.driverId,
                                          month: row.month,
                                          year: row.year,
                                          clCount: clText.isEmpty ? null : int.tryParse(clText),
                                          monthlySalary: double.parse(salaryController.text.trim()),
                                          notes: notesController.text.trim(),
                                        );
                                        if (!mounted) return;
                                        if (!success) {
                                          messenger.showSnackBar(
                                            SnackBar(
                                              content: Text(
                                                transporterProvider.error ?? 'Unable to pay salary.',
                                              ),
                                            ),
                                          );
                                          return;
                                        }
                                        navigator.pop();
                                        messenger.showSnackBar(
                                          const SnackBar(
                                            content: Text('Salary paid successfully.'),
                                          ),
                                        );
                                      },
                                icon: provider.loading
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.white,
                                        ),
                                      )
                                    : const Icon(Icons.payments_outlined),
                                label: Text(
                                  row.isPaid ? 'Paid' : (row.canPay ? 'Pay Salary' : 'Pay Locked'),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _openAdvanceSheet(DriverSalarySummary row) async {
    final provider = context.read<TransporterProvider>();
    await provider.loadSalaryAdvances(
      driverId: row.driverId,
      month: row.month,
      year: row.year,
      silent: true,
    );
    if (!mounted) {
      return;
    }

    final formKey = GlobalKey<FormState>();
    final amountController = TextEditingController();
    final notesController = TextEditingController();
    DateTime selectedDate = DateTime(row.year, row.month, 1);
    int? editingAdvanceId;

    Future<void> pickDate(StateSetter setSheetState) async {
      final picked = await showDatePicker(
        context: context,
        initialDate: selectedDate,
        firstDate: DateTime(row.year, row.month, 1),
        lastDate: DateTime(row.year, row.month + 1, 0),
      );
      if (picked == null) {
        return;
      }
      setSheetState(() {
        selectedDate = picked;
      });
    }

    void loadAdvanceIntoForm(SalaryAdvance advance, StateSetter setSheetState) {
      setSheetState(() {
        editingAdvanceId = advance.id;
        amountController.text = advance.amount.toStringAsFixed(2);
        notesController.text = advance.notes;
        selectedDate = advance.advanceDate;
      });
    }

    void clearAdvanceForm(StateSetter setSheetState) {
      setSheetState(() {
        editingAdvanceId = null;
        amountController.clear();
        notesController.clear();
        selectedDate = DateTime(row.year, row.month, 1);
      });
    }

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return Padding(
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
              ),
              child: FractionallySizedBox(
                heightFactor: 0.92,
                child: Container(
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
                  ),
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 18),
                  child: Consumer<TransporterProvider>(
                    builder: (context, transporterProvider, _) {
                      final advances = transporterProvider.salaryAdvances;
                      return Form(
                        key: formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Salary Advances',
                              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                    fontWeight: FontWeight.w700,
                                  ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '${row.driverName} - ${_monthLabel(DateTime(row.year, row.month, 1))}',
                              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                    color: Colors.black54,
                                  ),
                            ),
                            const SizedBox(height: 12),
                            Expanded(
                              child: SingleChildScrollView(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    if (advances.isEmpty)
                                      const Padding(
                                        padding: EdgeInsets.only(bottom: 14),
                                        child: Text('No advance recorded for this month.'),
                                      )
                                    else
                                      Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          ...advances.map((advance) {
                                            return Card(
                                              margin: const EdgeInsets.only(bottom: 10),
                                              child: ListTile(
                                                contentPadding: const EdgeInsets.symmetric(
                                                  horizontal: 14,
                                                  vertical: 4,
                                                ),
                                                title: Text(_money(advance.amount)),
                                                subtitle: Text(
                                                  '${_dateLabel(advance.advanceDate.toLocal())}'
                                                  '${advance.notes.isEmpty ? '' : ' | ${advance.notes}'}',
                                                ),
                                                trailing: TextButton(
                                                  onPressed: () => loadAdvanceIntoForm(
                                                    advance,
                                                    setSheetState,
                                                  ),
                                                  child: const Text('Edit'),
                                                ),
                                              ),
                                            );
                                          }),
                                          const SizedBox(height: 6),
                                        ],
                                      ),
                                    TextFormField(
                                      controller: amountController,
                                      keyboardType: const TextInputType.numberWithOptions(
                                        decimal: true,
                                      ),
                                      decoration: const InputDecoration(
                                        labelText: 'Advance Amount',
                                        prefixIcon: Icon(Icons.currency_rupee_rounded),
                                      ),
                                      validator: (value) {
                                        final parsed = double.tryParse((value ?? '').trim());
                                        if (parsed == null || parsed <= 0) {
                                          return 'Enter a valid advance amount';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 10),
                                    InkWell(
                                      onTap: () => pickDate(setSheetState),
                                      borderRadius: BorderRadius.circular(16),
                                      child: InputDecorator(
                                        decoration: const InputDecoration(
                                          labelText: 'Advance Date',
                                          prefixIcon: Icon(Icons.calendar_month_outlined),
                                        ),
                                        child: Text(_dateLabel(selectedDate)),
                                      ),
                                    ),
                                    const SizedBox(height: 10),
                                    TextFormField(
                                      controller: notesController,
                                      maxLines: 2,
                                      decoration: const InputDecoration(
                                        labelText: 'Notes (optional)',
                                        prefixIcon: Icon(Icons.sticky_note_2_outlined),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(height: 14),
                            Row(
                              children: [
                                if (editingAdvanceId != null) ...[
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: transporterProvider.loading
                                          ? null
                                          : () => clearAdvanceForm(setSheetState),
                                      child: const Text('Clear'),
                                    ),
                                  ),
                                  const SizedBox(width: 10),
                                ],
                                Expanded(
                                  child: FilledButton.icon(
                                    onPressed: transporterProvider.loading
                                        ? null
                                        : () async {
                                            if (!formKey.currentState!.validate()) {
                                              return;
                                            }
                                            final wasEditing = editingAdvanceId != null;
                                            final messenger = ScaffoldMessenger.of(context);
                                            final success = await transporterProvider.saveSalaryAdvance(
                                              advanceId: editingAdvanceId,
                                              driverId: row.driverId,
                                              amount: double.parse(amountController.text.trim()),
                                              advanceDate: selectedDate,
                                              notes: notesController.text.trim(),
                                              refreshMonth: row.month,
                                              refreshYear: row.year,
                                            );
                                            if (!mounted) {
                                              return;
                                            }
                                            if (!success) {
                                              messenger.showSnackBar(
                                                SnackBar(
                                                  content: Text(
                                                    transporterProvider.error ??
                                                        'Unable to save salary advance.',
                                                  ),
                                                ),
                                              );
                                              return;
                                            }
                                            clearAdvanceForm(setSheetState);
                                            messenger.showSnackBar(
                                              SnackBar(
                                                content: Text(
                                                  wasEditing
                                                      ? 'Advance updated successfully.'
                                                      : 'Advance added successfully.',
                                                ),
                                              ),
                                            );
                                          },
                                    icon: transporterProvider.loading
                                        ? const SizedBox(
                                            width: 16,
                                            height: 16,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: Colors.white,
                                            ),
                                          )
                                        : const Icon(Icons.save_outlined),
                                    label: Text(
                                      editingAdvanceId == null ? 'Add Advance' : 'Update Advance',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _metric(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: const TextStyle(fontSize: 11, color: Colors.black54)),
          const SizedBox(height: 2),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Driver Salary'),
        actions: [
          IconButton(onPressed: _pickMonth, icon: const Icon(Icons.calendar_month_outlined)),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE8F2F1), Color(0xFFF7EFE5)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            final summary = provider.salaryMonthlySummary;
            final visibleRows = summary == null
                ? const <DriverSalarySummary>[]
                : summary.rows
                    .where((row) => _showPaidRows || !row.isPaid)
                    .toList()
                  ..sort((a, b) {
                    if (a.isPaid != b.isPaid) {
                      return a.isPaid ? 1 : -1;
                    }
                    return a.driverName.toLowerCase().compareTo(
                          b.driverName.toLowerCase(),
                        );
                  });
            if (provider.loading && summary == null) {
              return const Center(child: CircularProgressIndicator());
            }
            if (provider.error != null && summary == null) {
              return Center(child: Text(provider.error!));
            }
            return RefreshIndicator(
              onRefresh: () => _loadAll(forceDashboard: true),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              IconButton(onPressed: () => _shiftMonth(-1), icon: const Icon(Icons.chevron_left_rounded)),
                              Expanded(
                                child: Column(
                                  children: [
                                    Text(_monthLabel(_selectedMonth), style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                                    const SizedBox(height: 2),
                                    Text(summary == null ? 'Loading...' : 'Salary due date: ${_dateLabel(summary.salaryDueDate)}', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.black54)),
                                  ],
                                ),
                              ),
                              IconButton(onPressed: () => _shiftMonth(1), icon: const Icon(Icons.chevron_right_rounded)),
                            ],
                          ),
                          if (summary != null) ...[
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                _metric('Drivers', '${summary.totalDrivers}'),
                                _metric('Paid', '${summary.paidCount}'),
                                _metric('Pending', '${summary.pendingCount}'),
                                _metric('Total Payable', _money(summary.totalPayableAmount)),
                                _metric('Total Paid', _money(summary.totalPaidAmount)),
                              ],
                            ),
                            const SizedBox(height: 10),
                            SwitchListTile.adaptive(
                              contentPadding: EdgeInsets.zero,
                              value: _showPaidRows,
                              onChanged: (value) {
                                setState(() {
                                  _showPaidRows = value;
                                });
                              },
                              title: const Text('Show Paid Salary Rows'),
                              subtitle: const Text('Default view shows only pending salary.'),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (summary == null || visibleRows.isEmpty)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              summary == null
                                  ? 'No driver salary data available for this month.'
                                  : (_showPaidRows
                                      ? 'No salary rows available for this month.'
                                      : 'No pending salary rows for this month.'),
                            ),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                OutlinedButton.icon(
                                  onPressed: _openPreviousMonth,
                                  icon: const Icon(Icons.history_outlined),
                                  label: const Text('Open Previous Month'),
                                ),
                                if (!_showPaidRows)
                                  FilledButton.icon(
                                    onPressed: () {
                                      setState(() {
                                        _showPaidRows = true;
                                      });
                                    },
                                    icon: const Icon(Icons.visibility_outlined),
                                    label: const Text('Show Paid Rows'),
                                  ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    )
                  else
                    ...visibleRows.map((row) {
                      return Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(row.driverName, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                                        const SizedBox(height: 2),
                                        Text(row.driverPhone.trim().isEmpty ? 'Phone not available' : row.driverPhone, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.black54)),
                                      ],
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                    decoration: BoxDecoration(
                                      color: (row.isPaid ? const Color(0xFF0B8A67) : const Color(0xFFE08D3C)).withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(999),
                                    ),
                                    child: Text(row.isPaid ? 'Paid' : 'Pending', style: TextStyle(color: row.isPaid ? const Color(0xFF0B8A67) : const Color(0xFFE08D3C), fontWeight: FontWeight.w700, fontSize: 12)),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  _metric('Salary', _money(row.monthlySalary)),
                                  _metric('Paid Days', '${row.paidDays}'),
                                  _metric('Present', '${row.presentDays}'),
                                  _metric('No Duty', '${row.noDutyDays}'),
                                  _metric('Weekly Off', '${row.weeklyOffDays}'),
                                  _metric('Leave', '${row.leaveDays}'),
                                  _metric('Absent', '${row.absentDays}'),
                                  _metric('Advance', _money(row.advanceAmount)),
                                  _metric('Net Payable', _money(row.netPayableAmount)),
                                ],
                              ),
                              const SizedBox(height: 10),
                              Text(
                                row.isPaid && row.paidAt != null
                                    ? 'Paid on ${_dateLabel(row.paidAt!.toLocal())}'
                                    : (row.canPay
                                        ? 'Due on ${_dateLabel(row.salaryDueDate)}'
                                        : 'Salary payment opens after month end.'),
                                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.black54),
                              ),
                              const SizedBox(height: 12),
                              Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                children: [
                                  OutlinedButton.icon(
                                    onPressed: () => _openAdvanceSheet(row),
                                    icon: const Icon(Icons.account_balance_wallet_outlined),
                                    label: const Text('Advances'),
                                  ),
                                  FilledButton.icon(
                                    onPressed: () => _openSalarySheet(row),
                                    icon: Icon(
                                      row.isPaid
                                          ? Icons.receipt_long_outlined
                                          : Icons.payments_outlined,
                                    ),
                                    label: Text(
                                      row.isPaid
                                          ? 'View Salary'
                                          : (row.canPay ? 'Pay Salary' : 'Salary Details'),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    }),
                  if (provider.loading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 10),
                      child: Center(child: CircularProgressIndicator()),
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


