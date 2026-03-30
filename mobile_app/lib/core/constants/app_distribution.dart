class AppDistribution {
  AppDistribution._();

  static const String channel = String.fromEnvironment(
    'APP_DISTRIBUTION_CHANNEL',
    defaultValue: 'direct',
  );

  static bool get isPlayStore => channel.trim().toLowerCase() == 'play';

  static bool get isDirectDistribution => !isPlayStore;
}
