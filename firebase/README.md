# Firebase files

| File | Used by | Purpose |
|------|---------|---------|
| `google-services.json` | **Android app** | Client SDK config (FCM on device) |
| `GoogleService-Info.plist` | **iOS app** | Client SDK config (FCM on device) |
| `*-firebase-adminsdk-*.json` | **API server** | Service account — sends push via FCM |

## Project: `youhoo-alert-app`

| Platform | Identifier | File |
|----------|------------|------|
| Android | `com.youhooalert.app` | `google-services.json` |
| iOS | `com.youhoolert.app` | `GoogleService-Info.plist` |

Both copied from Downloads into `firebase/`.

> **Note:** Android and iOS bundle IDs differ (`youhooalert` vs `youhoolert`). That is fine if intentional in Firebase; align them in the Firebase Console if you want one identifier everywhere.

## Android app setup

Copy into your Android project:

```
android/app/google-services.json
```

## iOS app setup

Copy into your Xcode project (drag into the app target, ensure “Copy items if needed”):

```
ios/Runner/GoogleService-Info.plist   # Flutter
ios/YourApp/GoogleService-Info.plist  # native / Expo prebuild
```

For **APNs push** on iOS, also upload your APNs key in Firebase Console → Project settings → Cloud Messaging → Apple app configuration.

## API server setup (FCM push)

Client plist/json files **cannot** send pushes from the server. You still need:

1. Firebase Console → **Project settings** → **Service accounts**
2. **Generate new private key** → save as e.g. `youhoo-alert-app-firebase-adminsdk.json`
3. Add to `.env`:

```env
FCM_ENABLED=true
FIREBASE_PROJECT_ID=youhoo-alert-app
FIREBASE_CREDENTIALS_PATH=firebase/youhoo-alert-app-firebase-adminsdk.json
```

On Vercel, use `FIREBASE_CREDENTIALS_JSON` with the full JSON string instead of a file path.
