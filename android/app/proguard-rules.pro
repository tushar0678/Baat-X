# Kotlinx serialization
-keepattributes *Annotation*, InnerClasses, Signature
-dontnote kotlinx.serialization.**
-keepclassmembers class com.baatx.data.remote.dto.** { *; }
-keepclasseswithmembers class ** {
    @kotlinx.serialization.Serializable <methods>;
}

# Retrofit / OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keepclasseswithmembers class * { @retrofit2.http.* <methods>; }

# Room
-keep class androidx.room.** { *; }

# Never keep debug logging in release builds.
-assumenosideeffects class android.util.Log {
    public static *** d(...);
    public static *** v(...);
}
