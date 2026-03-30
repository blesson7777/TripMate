# TripMate Play Store Deployment

## What is ready in code

- Separate Play flavors:
  - `driverPlay`
  - `transporterPlay`
- In-app APK updater is disabled for Play builds.
- Driver app keeps trip background location support for Play review.
- Privacy policy page:
  - `/privacy-policy/`
- Account deletion page:
  - `/account-deletion/`
- In-app account deletion request is available from both profile screens.

## Keystore setup

1. Copy `mobile_app/android/key.properties.example` to `mobile_app/android/key.properties`
2. Fill in:
   - `storeFile`
   - `storePassword`
   - `keyAlias`
   - `keyPassword`
3. Keep the `.jks` file and passwords safe. Future Play updates need the same upload key.

## Build commands

From `mobile_app/`:

```powershell
.\build_play_store_bundles.ps1
```

Outputs:

- `mobile_app/build/app/outputs/bundle/driverPlayRelease/app-driverPlay-release.aab`
- `mobile_app/build/app/outputs/bundle/transporterPlayRelease/app-transporterPlay-release.aab`

## Play Console notes

- Personal developer accounts may need a closed test before production.
- Driver app background location will need:
  - prominent disclosure
  - privacy policy
  - Data safety answers
  - Play background-location declaration
  - reviewer instructions and demo login
- Transporter app should avoid unnecessary sensitive permissions in the Play build.

## Suggested release strategy

- `TripMate Driver` → Play listing package: `com.tripmate.driver`
- `TripMate Transporter` → Play listing package: `com.tripmate.transporter`
- Start with **Closed Testing**
- After review passes, move to **Production**
