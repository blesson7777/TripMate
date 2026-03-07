class Trip {
  const Trip({
    required this.id,
    this.attendanceId,
    this.attendanceDate,
    this.attendanceStatus,
    this.attendanceServiceId,
    this.attendanceServiceName,
    this.attendanceServicePurpose,
    this.attendanceStartedAt,
    this.attendanceEndedAt,
    this.attendanceStartKm,
    this.attendanceEndKm,
    this.attendanceLatitude,
    this.attendanceLongitude,
    this.openingOdoImage,
    this.closingOdoImage,
    this.driverName,
    this.vehicleNumber,
    this.tripStatus,
    this.isDayTrip = false,
    this.tripStartedAt,
    this.tripEndedAt,
    this.isLive = false,
    required this.startLocation,
    required this.destination,
    required this.startKm,
    required this.endKm,
    required this.totalKm,
    required this.createdAt,
    this.purpose,
  });

  final int id;
  final int? attendanceId;
  final DateTime? attendanceDate;
  final String? attendanceStatus;
  final int? attendanceServiceId;
  final String? attendanceServiceName;
  final String? attendanceServicePurpose;
  final DateTime? attendanceStartedAt;
  final DateTime? attendanceEndedAt;
  final int? attendanceStartKm;
  final int? attendanceEndKm;
  final double? attendanceLatitude;
  final double? attendanceLongitude;
  final String? openingOdoImage;
  final String? closingOdoImage;
  final String? driverName;
  final String? vehicleNumber;
  final String? tripStatus;
  final bool isDayTrip;
  final DateTime? tripStartedAt;
  final DateTime? tripEndedAt;
  final bool isLive;
  final String startLocation;
  final String destination;
  final int startKm;
  final int endKm;
  final int totalKm;
  final DateTime createdAt;
  final String? purpose;
}
