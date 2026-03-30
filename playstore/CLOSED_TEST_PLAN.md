# TripMate Closed Test Plan

For a personal developer account, use this plan if Google requires closed testing.

## Target testers

- 12 active testers minimum
- Mix of:
  - 4 drivers
  - 4 transporter-side users
  - 4 internal testers/admin testers

## Test duration

- 14 continuous days minimum

## What testers should verify

### Driver app

- Login
- Start Day
- Odometer photo flow
- Fuel entry
- Tower diesel entry
- Notifications
- End Day
- Trip history

### Transporter app

- Login
- Dashboard data load
- Trips and attendance
- Live tracking map
- Fuel records
- Reports
- Vehicle bill screen

## Daily test checklist

- At least one login per app
- At least one trip opened and closed in Driver
- At least one live tracking check in Transporter
- At least one fuel or diesel entry
- At least one report or bill open

## Exit criteria

- No login blocker
- No crash loop
- No blank map in transporter live tracking
- Notifications arrive reliably
- Start Day / End Day workflow works end to end
