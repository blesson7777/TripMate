import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/constants/public_links.dart';
import '../../../core/utils/field_validators.dart';
import '../../../domain/entities/driver_profile.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/email_otp_confirmation_sheet.dart';
import '../../widgets/profile_page_sections.dart';
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
    final emailOtpController = TextEditingController();
    final licenseController =
        TextEditingController(text: profile.licenseNumber);
    final originalEmail = profile.user.email.trim().toLowerCase();
    bool otpSent = false;

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
          child: StatefulBuilder(
            builder: (context, setSheetState) {
              Future<void> sendEmailOtp() async {
                final nextEmail = emailController.text.trim().toLowerCase();
                if (nextEmail.isEmpty) {
                  ScaffoldMessenger.of(sheetContext).showSnackBar(
                    const SnackBar(content: Text('Email is required.')),
                  );
                  return;
                }
                if (validateEmailAddress(nextEmail) != null) {
                  ScaffoldMessenger.of(sheetContext).showSnackBar(
                    const SnackBar(
                      content: Text('Enter a valid email address.'),
                    ),
                  );
                  return;
                }
                if (nextEmail == originalEmail) {
                  ScaffoldMessenger.of(sheetContext).showSnackBar(
                    const SnackBar(
                      content: Text('Enter a new email to receive OTP.'),
                    ),
                  );
                  return;
                }

                final auth = sheetContext.read<AuthProvider>();
                final sent =
                    await auth.requestProfileEmailChangeOtp(email: nextEmail);
                if (!sheetContext.mounted) {
                  return;
                }
                if (!sent) {
                  ScaffoldMessenger.of(sheetContext).showSnackBar(
                    SnackBar(
                      content: Text(auth.error ?? 'Unable to send OTP.'),
                    ),
                  );
                  return;
                }
                setSheetState(() {
                  otpSent = true;
                });
                ScaffoldMessenger.of(sheetContext).showSnackBar(
                  SnackBar(content: Text('OTP sent to $nextEmail')),
                );
              }

              final emailChanged =
                  emailController.text.trim().toLowerCase() != originalEmail;
              return Container(
                decoration: const BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
                ),
                padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
                child: Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Edit Driver Profile',
                          style: Theme.of(sheetContext).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: usernameController,
                          decoration: const InputDecoration(
                            labelText: 'Username',
                          ),
                          validator: (value) =>
                              (value == null || value.trim().isEmpty)
                                  ? 'Username is required'
                                  : null,
                        ),
                        const SizedBox(height: 12),
                        ReadOnlyProfileField(
                          label: 'Primary mobile number',
                          value: profile.user.phone.trim().isEmpty
                              ? 'Not available'
                              : profile.user.phone,
                          helper:
                              'Phone number editing is locked in profile. Contact admin/support if it must be changed.',
                          icon: Icons.call_outlined,
                        ),
                        const SizedBox(height: 12),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: emailController,
                                keyboardType: TextInputType.emailAddress,
                                onChanged: (_) => setSheetState(() {
                                  otpSent = false;
                                  emailOtpController.clear();
                                }),
                                decoration: const InputDecoration(
                                  labelText: 'Email',
                                ),
                                validator: validateEmailAddress,
                              ),
                            ),
                            const SizedBox(width: 12),
                            SizedBox(
                              width: 128,
                              height: 52,
                              child: Consumer<AuthProvider>(
                                builder: (context, auth, _) {
                                  return FilledButton.tonalIcon(
                                    onPressed:
                                        auth.isLoading ? null : sendEmailOtp,
                                    icon: const Icon(
                                        Icons.mark_email_read_outlined),
                                    label: Text(
                                        otpSent ? 'Resend OTP' : 'Send OTP'),
                                  );
                                },
                              ),
                            ),
                          ],
                        ),
                        if (emailChanged) ...[
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: emailOtpController,
                            keyboardType: TextInputType.number,
                            maxLength: 6,
                            decoration: InputDecoration(
                              labelText: 'Email OTP',
                              counterText: '',
                              helperText: otpSent
                                  ? 'Enter the OTP sent to the new email address.'
                                  : 'Send OTP to the new email before saving.',
                            ),
                            validator: (value) {
                              final text = value?.trim() ?? '';
                              if (text.length != 6) {
                                return 'Enter the 6-digit email OTP';
                              }
                              return null;
                            },
                          ),
                        ],
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: licenseController,
                          textCapitalization: TextCapitalization.characters,
                          decoration: const InputDecoration(
                            labelText: 'License Number',
                            hintText: 'KL0720110012345',
                          ),
                          validator: validateIndianLicenseNumber,
                        ),
                        const SizedBox(height: 16),
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
                                            username:
                                                usernameController.text.trim(),
                                            email: emailController.text.trim(),
                                            emailOtp: emailChanged
                                                ? emailOtpController.text.trim()
                                                : null,
                                            licenseNumber:
                                                normalizeIndianLicenseNumber(
                                              licenseController.text,
                                            ),
                                          );

                                      if (!context.mounted) {
                                        return;
                                      }

                                      if (!success) {
                                        ScaffoldMessenger.of(context)
                                            .showSnackBar(
                                          SnackBar(
                                            content: Text(
                                              context
                                                      .read<AuthProvider>()
                                                      .error ??
                                                  'Unable to update profile',
                                            ),
                                          ),
                                        );
                                        return;
                                      }

                                      Navigator.pop(context);
                                      ScaffoldMessenger.of(context)
                                          .showSnackBar(
                                        SnackBar(
                                          content: Text(
                                            emailChanged
                                                ? 'Profile updated and email verified successfully.'
                                                : 'Profile updated successfully',
                                          ),
                                        ),
                                      );
                                    },
                              icon: auth.isLoading
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 2),
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

  Future<void> _openPublicLink(Uri uri) async {
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to open link right now.')),
      );
    }
  }

  Future<void> _requestAccountDeletion() async {
    final auth = context.read<AuthProvider>();
    final emailAddress = auth.user?.email.trim() ?? '';
    if (emailAddress.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'A registered email address is required to delete this account.',
          ),
        ),
      );
      return;
    }

    final otpCode = await showEmailOtpConfirmationSheet(
      context: context,
      emailAddress: emailAddress,
      title: 'Delete Driver Account',
      confirmLabel: 'Delete Account',
      subtitle:
          'This will permanently close this driver account after email OTP verification.',
    );
    if (otpCode == null || !mounted) {
      return;
    }

    final success = await context.read<AuthProvider>().requestAccountDeletion(
          otp: otpCode,
        );
    if (!mounted) {
      return;
    }

    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.read<AuthProvider>().error ??
                'Unable to delete the account right now.',
          ),
        ),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Account deleted successfully. You have been signed out.',
        ),
      ),
    );
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  Future<void> _confirmLogout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Logout'),
          content: const Text('Do you want to logout from this device?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Logout'),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) {
      return;
    }
    context.read<AuthProvider>().logout();
    Navigator.of(context).popUntil((route) => route.isFirst);
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
                  physics: const AlwaysScrollableScrollPhysics(
                    parent: BouncingScrollPhysics(),
                  ),
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
                  children: [
                    Row(
                      children: [
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.76),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: IconButton(
                            onPressed: () => Navigator.pop(context),
                            icon: const Icon(Icons.arrow_back_rounded),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Driver Profile',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleLarge
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              Text(
                                'Manage your account and assignment details',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(
                                      color: colors.onSurface
                                          .withValues(alpha: 0.62),
                                    ),
                              ),
                            ],
                          ),
                        ),
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.82),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: IconButton(
                            tooltip: 'Logout',
                            onPressed: _confirmLogout,
                            icon: Icon(
                              Icons.logout_rounded,
                              color: colors.error,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
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
                        child: ProfileSectionCard(
                          padding: const EdgeInsets.all(20),
                          gradient: LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [
                              Colors.white.withValues(alpha: 0.98),
                              const Color(0xFFEAF4FF),
                              const Color(0xFFF4F9F0),
                            ],
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Container(
                                    width: 72,
                                    height: 72,
                                    decoration: BoxDecoration(
                                      color: colors.primary
                                          .withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(24),
                                      border: Border.all(
                                        color: colors.primary
                                            .withValues(alpha: 0.16),
                                      ),
                                    ),
                                    alignment: Alignment.center,
                                    child: Icon(
                                      Icons.person_rounded,
                                      size: 36,
                                      color: colors.primary,
                                    ),
                                  ),
                                  const SizedBox(width: 16),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          profile.user.username,
                                          style: Theme.of(context)
                                              .textTheme
                                              .headlineSmall
                                              ?.copyWith(
                                                fontWeight: FontWeight.w800,
                                              ),
                                        ),
                                        const SizedBox(height: 6),
                                        Text(
                                          'Driver Account',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodyMedium
                                              ?.copyWith(
                                                color: colors.onSurface
                                                    .withValues(alpha: 0.68),
                                              ),
                                        ),
                                        const SizedBox(height: 12),
                                        Wrap(
                                          spacing: 8,
                                          runSpacing: 8,
                                          children: [
                                            ProfileStatusBadge(
                                              label: profile.isActive
                                                  ? 'Active'
                                                  : 'Inactive',
                                              icon: profile.isActive
                                                  ? Icons.verified_rounded
                                                  : Icons.pause_circle_outline,
                                              color: profile.isActive
                                                  ? const Color(0xFF148A56)
                                                  : colors.error,
                                            ),
                                            ProfileStatusBadge(
                                              label:
                                                  '#${profile.id.toString().padLeft(4, '0')}',
                                              icon: Icons.badge_outlined,
                                              color: colors.primary,
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 18),
                              Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                children: [
                                  _ContactChip(
                                    icon: Icons.call_outlined,
                                    label: profile.user.phone.trim().isEmpty
                                        ? 'Phone not available'
                                        : profile.user.phone,
                                  ),
                                  _ContactChip(
                                    icon: Icons.mail_outline_rounded,
                                    label: profile.user.email.trim().isEmpty
                                        ? 'Email not available'
                                        : profile.user.email,
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 130),
                        child: ProfileSectionCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Assignment Overview',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 14),
                              LayoutBuilder(
                                builder: (context, constraints) {
                                  final columns =
                                      constraints.maxWidth >= 720 ? 3 : 1;
                                  final spacing = 12.0;
                                  final itemWidth = columns == 1
                                      ? constraints.maxWidth
                                      : (constraints.maxWidth -
                                              ((columns - 1) * spacing)) /
                                          columns;

                                  return Wrap(
                                    spacing: spacing,
                                    runSpacing: spacing,
                                    children: [
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileMetricTile(
                                          icon: Icons.business_center_outlined,
                                          label: 'Transporter',
                                          value:
                                              (profile.transporterCompanyName !=
                                                          null &&
                                                      profile
                                                          .transporterCompanyName!
                                                          .trim()
                                                          .isNotEmpty)
                                                  ? profile
                                                      .transporterCompanyName!
                                                  : 'Not assigned',
                                          highlightColor:
                                              const Color(0xFF5B5BD6),
                                        ),
                                      ),
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileMetricTile(
                                          icon: Icons.local_shipping_outlined,
                                          label: 'Vehicle',
                                          value:
                                              profile.assignedVehicleNumber ??
                                                  'Not assigned',
                                          highlightColor:
                                              const Color(0xFF118AB2),
                                        ),
                                      ),
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileMetricTile(
                                          icon: Icons.route_outlined,
                                          label: 'Service',
                                          value: (profile.defaultServiceName ??
                                                  '')
                                              .trim()
                                              .isEmpty
                                              ? 'Not assigned'
                                              : profile.defaultServiceName!,
                                          highlightColor:
                                              const Color(0xFFF59E0B),
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 180),
                        child: ProfileSectionCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Account Details',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 14),
                              LayoutBuilder(
                                builder: (context, constraints) {
                                  final columns =
                                      constraints.maxWidth >= 620 ? 2 : 1;
                                  final spacing = 12.0;
                                  final itemWidth = columns == 1
                                      ? constraints.maxWidth
                                      : (constraints.maxWidth -
                                              ((columns - 1) * spacing)) /
                                          columns;

                                  return Wrap(
                                    spacing: spacing,
                                    runSpacing: spacing,
                                    children: [
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileInfoTile(
                                          icon: Icons.phone_iphone_rounded,
                                          label: 'Phone',
                                          value:
                                              profile.user.phone.trim().isEmpty
                                                  ? 'Not set'
                                                  : profile.user.phone,
                                        ),
                                      ),
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileInfoTile(
                                          icon: Icons.mail_outline_rounded,
                                          label: 'Email',
                                          value: profile.user.email,
                                        ),
                                      ),
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileInfoTile(
                                          icon:
                                              Icons.credit_card_outlined,
                                          label: 'License Number',
                                          value:
                                              profile.licenseNumber.trim().isEmpty
                                                  ? 'Not set'
                                                  : profile.licenseNumber,
                                        ),
                                      ),
                                      SizedBox(
                                        width: itemWidth,
                                        child: ProfileInfoTile(
                                          icon: Icons.shield_outlined,
                                          label: 'Account Status',
                                          value: profile.isActive
                                              ? 'Ready for duty'
                                              : 'Inactive',
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      StaggeredEntrance(
                        delay: const Duration(milliseconds: 230),
                        child: ProfileSectionCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Quick Actions',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 14),
                              ProfileActionGrid(
                                children: [
                                  ProfileActionTile(
                                    icon: Icons.edit_rounded,
                                    title: 'Edit Profile',
                                    onTap: () => _openEditProfileSheet(profile),
                                    isPrimary: true,
                                  ),
                                  ProfileActionTile(
                                    icon: Icons.lock_reset_rounded,
                                    title: 'Password',
                                    onTap: _openPasswordSheet,
                                  ),
                                  ProfileActionTile(
                                    icon: Icons.privacy_tip_outlined,
                                    title: 'Privacy',
                                    onTap: () => _openPublicLink(
                                        PublicLinks.privacyPolicy),
                                  ),
                                  ProfileActionTile(
                                    icon: Icons.open_in_new_outlined,
                                    title: 'Deletion Help',
                                    onTap: () => _openPublicLink(
                                        PublicLinks.accountDeletion),
                                  ),
                                  ProfileActionTile(
                                    icon: Icons.delete_outline_rounded,
                                    title: 'Delete Account',
                                    onTap: auth.isLoading
                                        ? null
                                        : _requestAccountDeletion,
                                    isDestructive: true,
                                    isEnabled: !auth.isLoading,
                                  ),
                                ],
                              ),
                            ],
                          ),
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

class _ContactChip extends StatelessWidget {
  const _ContactChip({
    required this.icon,
    required this.label,
  });

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: colors.primary.withValues(alpha: 0.14),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: colors.primary),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
