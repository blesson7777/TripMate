import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/driver_profile.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/staggered_entrance.dart';

class DriverProfileScreen extends StatefulWidget {
  const DriverProfileScreen({super.key});

  @override
  State<DriverProfileScreen> createState() => _DriverProfileScreenState();
}

class _DriverProfileScreenState extends State<DriverProfileScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadProfile());
  }

  Future<void> _loadProfile() async {
    await context.read<AuthProvider>().loadDriverProfile();
  }

  Future<void> _openEditProfileSheet(DriverProfile profile) async {
    final formKey = GlobalKey<FormState>();
    final usernameController =
        TextEditingController(text: profile.user.username);
    final emailController = TextEditingController(text: profile.user.email);
    final phoneController = TextEditingController(text: profile.user.phone);
    final licenseController =
        TextEditingController(text: profile.licenseNumber);

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
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Edit Driver Profile',
                    style: Theme.of(sheetContext).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: usernameController,
                    decoration: const InputDecoration(labelText: 'Username'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                            ? 'Username is required'
                            : null,
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Email'),
                    validator: (value) {
                      final text = value?.trim() ?? '';
                      if (text.isEmpty) {
                        return 'Email is required';
                      }
                      final valid =
                          RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(text);
                      if (!valid) {
                        return 'Enter a valid email';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: phoneController,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(labelText: 'Phone'),
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: licenseController,
                    decoration:
                        const InputDecoration(labelText: 'License Number'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                            ? 'License number is required'
                            : null,
                  ),
                  const SizedBox(height: 14),
                  Consumer<AuthProvider>(
                    builder: (context, auth, _) {
                      return FilledButton.icon(
                        onPressed: auth.isLoading
                            ? null
                            : () async {
                                if (!formKey.currentState!.validate()) {
                                  return;
                                }
                                final success = await context
                                    .read<AuthProvider>()
                                    .updateDriverProfile(
                                      username: usernameController.text.trim(),
                                      email: emailController.text.trim(),
                                      phone: phoneController.text.trim(),
                                      licenseNumber:
                                          licenseController.text.trim(),
                                    );

                                if (!context.mounted) {
                                  return;
                                }

                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context.read<AuthProvider>().error ??
                                            'Unable to update profile',
                                      ),
                                    ),
                                  );
                                  return;
                                }

                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content:
                                        Text('Profile updated successfully'),
                                  ),
                                );
                              },
                        icon: auth.isLoading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.save_outlined),
                        label: const Text('Save Changes'),
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

  Future<void> _openPasswordSheet() async {
    final formKey = GlobalKey<FormState>();
    final currentController = TextEditingController();
    final newController = TextEditingController();
    final confirmController = TextEditingController();
    bool obscureCurrent = true;
    bool obscureNew = true;
    bool obscureConfirm = true;

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
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
            child: StatefulBuilder(
              builder: (context, setSheetState) => Form(
                key: formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Change Password',
                      style: Theme.of(sheetContext).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: currentController,
                      obscureText: obscureCurrent,
                      decoration: InputDecoration(
                        labelText: 'Current Password',
                        suffixIcon: IconButton(
                          onPressed: () {
                            setSheetState(() {
                              obscureCurrent = !obscureCurrent;
                            });
                          },
                          icon: Icon(
                            obscureCurrent
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: (value) => (value == null || value.isEmpty)
                          ? 'Current password is required'
                          : null,
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: newController,
                      obscureText: obscureNew,
                      decoration: InputDecoration(
                        labelText: 'New Password',
                        suffixIcon: IconButton(
                          onPressed: () {
                            setSheetState(() {
                              obscureNew = !obscureNew;
                            });
                          },
                          icon: Icon(
                            obscureNew
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: (value) {
                        final text = value ?? '';
                        if (text.isEmpty) {
                          return 'New password is required';
                        }
                        if (text.length < 8) {
                          return 'Password must be at least 8 characters';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: confirmController,
                      obscureText: obscureConfirm,
                      decoration: InputDecoration(
                        labelText: 'Confirm Password',
                        suffixIcon: IconButton(
                          onPressed: () {
                            setSheetState(() {
                              obscureConfirm = !obscureConfirm;
                            });
                          },
                          icon: Icon(
                            obscureConfirm
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Confirm password is required';
                        }
                        if (value != newController.text) {
                          return 'Passwords do not match';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 14),
                    Consumer<AuthProvider>(
                      builder: (context, auth, _) {
                        return FilledButton.icon(
                          onPressed: auth.isLoading
                              ? null
                              : () async {
                                  if (!formKey.currentState!.validate()) {
                                    return;
                                  }
                                  final success = await context
                                      .read<AuthProvider>()
                                      .changePassword(
                                        currentPassword:
                                            currentController.text.trim(),
                                        newPassword: newController.text.trim(),
                                        confirmPassword:
                                            confirmController.text.trim(),
                                      );
                                  if (!context.mounted) {
                                    return;
                                  }

                                  if (!success) {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(
                                        content: Text(
                                          context.read<AuthProvider>().error ??
                                              'Unable to change password',
                                        ),
                                      ),
                                    );
                                    return;
                                  }

                                  Navigator.pop(context);
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(
                                      content:
                                          Text('Password changed successfully'),
                                    ),
                                  );
                                },
                          icon: auth.isLoading
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.lock_reset_outlined),
                          label: const Text('Update Password'),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFFF9F1E2),
              Color(0xFFE6F0EF),
              Color(0xFFD9E7F0),
            ],
          ),
        ),
        child: SafeArea(
          child: Consumer<AuthProvider>(
            builder: (context, auth, _) {
              final profile = auth.driverProfile;

              return RefreshIndicator(
                onRefresh: _loadProfile,
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Row(
                      children: [
                        IconButton(
                          onPressed: () => Navigator.pop(context),
                          icon: const Icon(Icons.arrow_back_rounded),
                        ),
                        Text(
                          'Driver Profile',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    if (auth.isLoading && profile == null)
                      const Padding(
                        padding: EdgeInsets.only(top: 30),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    else if (profile == null)
                      Padding(
                        padding: const EdgeInsets.only(top: 30),
                        child: Text(
                          auth.error ?? 'Unable to load profile',
                          style: TextStyle(color: colors.error),
                        ),
                      )
                    else ...[
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 80),
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Row(
                              children: [
                                Container(
                                  width: 52,
                                  height: 52,
                                  decoration: BoxDecoration(
                                    color:
                                        colors.primary.withValues(alpha: 0.12),
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                  child: Icon(
                                    Icons.person_rounded,
                                    color: colors.primary,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        profile.user.username,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                              fontWeight: FontWeight.w700,
                                            ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(profile.user.email),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 10),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 130),
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              children: [
                                _ProfileRow(
                                  label: 'Phone',
                                  value: profile.user.phone.isEmpty
                                      ? 'Not set'
                                      : profile.user.phone,
                                ),
                                _ProfileRow(
                                  label: 'License Number',
                                  value: profile.licenseNumber,
                                ),
                                _ProfileRow(
                                  label: 'Transporter',
                                  value:
                                      (profile.transporterCompanyName != null &&
                                              profile.transporterCompanyName!
                                                  .trim()
                                                  .isNotEmpty)
                                          ? profile.transporterCompanyName!
                                          : 'Not assigned',
                                ),
                                _ProfileRow(
                                  label: 'Assigned Vehicle',
                                  value: profile.assignedVehicleNumber ??
                                      'Not assigned',
                                  isLast: true,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 180),
                        child: FilledButton.icon(
                          onPressed: () => _openEditProfileSheet(profile),
                          icon: const Icon(Icons.edit_rounded),
                          label: const Text('Edit Profile'),
                        ),
                      ),
                      const SizedBox(height: 10),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 220),
                        child: OutlinedButton.icon(
                          onPressed: _openPasswordSheet,
                          icon: const Icon(Icons.lock_reset_rounded),
                          label: const Text('Change Password'),
                        ),
                      ),
                      const SizedBox(height: 10),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 260),
                        child: FilledButton.tonalIcon(
                          onPressed: () {
                            context.read<AuthProvider>().logout();
                            Navigator.of(context)
                                .popUntil((route) => route.isFirst);
                          },
                          icon: const Icon(Icons.logout_rounded),
                          label: const Text('Logout'),
                        ),
                      ),
                    ],
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ProfileRow extends StatelessWidget {
  const _ProfileRow({
    required this.label,
    required this.value,
    this.isLast = false,
  });

  final String label;
  final String value;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 11),
      decoration: BoxDecoration(
        border: isLast
            ? null
            : Border(
                bottom: BorderSide(
                  color: Colors.black.withValues(alpha: 0.08),
                ),
              ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Colors.black.withValues(alpha: 0.62),
                  ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
