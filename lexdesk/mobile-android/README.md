# LexDesk for Android

The app shows the firm's LexDesk full screen, so every change on the server
appears in the app at once, with no app update. On the phone it adds:

- WhatsApp, phone, email and social media links open in their own apps.
- Documents open in the phone's viewer and are saved to `Downloads/LexDesk`.
- Uploading files and photos from the phone.
- **Offline court mode**: briefs saved for court open with no signal, from
  the "Open saved court briefs" button, or automatically when the phone has
  no connection at start-up.
- If the server cannot be reached, a screen offers to retry, open saved
  briefs, or change the server address.

## Build for testing (this computer)

```powershell
$env:JAVA_HOME = "C:\Users\user\Downloads\jdk-17.0.12_windows-x64_bin\jdk-17.0.12"
gradle assembleDebug -PlexdeskServer=http://192.168.1.64:3000
# -> app\build\outputs\apk\debug\app-debug.apk
```

## Build for release (Play Store or direct install)

1. Create the signing key **once**, and keep it with the `.env` backups. If
   it is lost, the app can never be updated on the Play Store.

   ```powershell
   keytool -genkeypair -v -keystore lexdesk-release.jks -alias lexdesk -keyalg RSA -keysize 4096 -validity 10000
   ```

2. Create `keystore.properties` here (it is git-ignored):

   ```
   storeFile=../lexdesk-release.jks
   storePassword=...
   keyAlias=lexdesk
   keyPassword=...
   ```

3. Build with the live address, and raise `versionCode` in `app/build.gradle`
   for every new release:

   ```powershell
   gradle assembleRelease -PlexdeskServer=https://lexdesk.co.ug
   gradle bundleRelease  -PlexdeskServer=https://lexdesk.co.ug   # .aab for the Play Store
   ```

Once the app points at an `https` address, remove `usesCleartextTraffic` and
the network security config from `AndroidManifest.xml`: they exist only for
testing on the office Wi-Fi.

## Note on this network

This computer's network inspects HTTPS traffic, so Gradle uses the Windows
certificate store (`gradle.properties`). On a normal network that line is
harmless.
