# Android — 2 edits

These two are small enough to do by hand; no need to replace whole files.

## 1. `android/app/build.gradle.kts`

Find `targetSdk = 35` inside the `defaultConfig { }` block:

```diff
     defaultConfig {
         applicationId = "com.baatx"
         minSdk = 26
-        targetSdk = 35
+        targetSdk = 36
         versionCode = 1
```

Required for new Google Play submissions. Skip it if you're only sideloading
the APK for now — but retest on a real device after changing it, since API 36
tightens several platform defaults.

## 2. `android/app/src/main/java/com/baatx/core/network/NetworkModule.kt`

**Only if you deploy on Render's free plan.** Find the `okHttp` provider:

```diff
         .connectTimeout(30, TimeUnit.SECONDS)
+        // Free-tier cold start: the container can take ~60s to wake.
+        // Revert to 30s once you're on Starter — a long timeout otherwise
+        // hides real network failures behind a spinner.
         .readTimeout(120, TimeUnit.SECONDS)
```

becomes:

```kotlin
        .connectTimeout(90, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
```

## Build against your deployed API

```powershell
cd android
gradle wrapper --gradle-version 8.12    # one-time; wrapper JAR isn't in the zip
$env:BAATX_API_BASE_URL = "https://baatx-api.onrender.com/"
./gradlew assembleDebug
```

APK: `app/build/outputs/apk/debug/`
