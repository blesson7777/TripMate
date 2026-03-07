import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class ServicesScreen extends StatefulWidget {
  const ServicesScreen({super.key});

  @override
  State<ServicesScreen> createState() => _ServicesScreenState();
}

class _ServicesScreenState extends State<ServicesScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadDashboardData();
    });
  }

  Future<void> _openAddServiceSheet() async {
    final formKey = GlobalKey<FormState>();
    final nameController = TextEditingController();
    final descriptionController = TextEditingController();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
          ),
          child: Container(
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Add Service',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: nameController,
                    decoration: const InputDecoration(
                      labelText: 'Service Name',
                      prefixIcon: Icon(Icons.miscellaneous_services_outlined),
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Service name is required';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: descriptionController,
                    decoration: const InputDecoration(
                      labelText: 'Description (optional)',
                      prefixIcon: Icon(Icons.description_outlined),
                    ),
                    maxLines: 2,
                  ),
                  const SizedBox(height: 14),
                  Consumer<TransporterProvider>(
                    builder: (context, provider, _) {
                      return FilledButton.icon(
                        onPressed: provider.loading
                            ? null
                            : () async {
                                if (!formKey.currentState!.validate()) {
                                  return;
                                }
                                final success = await context
                                    .read<TransporterProvider>()
                                    .addService(
                                      name: nameController.text.trim(),
                                      description:
                                          descriptionController.text.trim(),
                                      isActive: true,
                                    );
                                if (!context.mounted) {
                                  return;
                                }
                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context
                                                .read<TransporterProvider>()
                                                .error ??
                                            'Unable to add service',
                                      ),
                                    ),
                                  );
                                  return;
                                }
                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Service added successfully'),
                                  ),
                                );
                              },
                        icon: provider.loading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.add_rounded),
                        label: const Text('Add Service'),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _toggleService(
    int serviceId,
    bool newValue,
  ) async {
    final success = await context.read<TransporterProvider>().updateService(
          serviceId: serviceId,
          isActive: newValue,
        );
    if (!mounted) {
      return;
    }
    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.read<TransporterProvider>().error ??
                'Unable to update service.',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Service Management')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAddServiceSheet,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Add Service'),
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE8F2F1), Color(0xFFF4EFE6)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            if (provider.loading && provider.services.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }
            if (provider.error != null && provider.services.isEmpty) {
              return Center(child: Text(provider.error!));
            }
            if (provider.services.isEmpty) {
              return const _EmptyState(
                icon: Icons.miscellaneous_services_outlined,
                message: 'No services configured yet.',
              );
            }

            return RefreshIndicator(
              onRefresh: () => provider.loadDashboardData(force: true),
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                itemCount: provider.services.length,
                itemBuilder: (context, index) {
                  final service = provider.services[index];
                  return StaggeredEntrance(
                    delay: Duration(milliseconds: 55 * index),
                    child: Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: ListTile(
                        leading: Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            color:
                                const Color(0xFF0A6B6F).withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.miscellaneous_services_outlined,
                            color: Color(0xFF0A6B6F),
                          ),
                        ),
                        title: Text(service.name),
                        subtitle: Text(
                          service.description.isEmpty
                              ? 'No description'
                              : service.description,
                        ),
                        trailing: Switch(
                          value: service.isActive,
                          onChanged: provider.loading
                              ? null
                              : (value) => _toggleService(service.id, value),
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
