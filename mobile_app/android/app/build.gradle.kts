import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    FileInputStream(keystorePropertiesFile).use { keystoreProperties.load(it) }
}

fun signingValue(name: String): String {
    return keystoreProperties.getProperty(name)
        ?: System.getenv("TRIPMATE_${name.uppercase()}")
        ?: ""
}

val playStoreSigningReady = listOf(
    "storeFile",
    "storePassword",
    "keyAlias",
    "keyPassword",
).all { signingValue(it).isNotBlank() }

android {
    namespace = "com.example.tripmate_mobile"
    compileSdk = maxOf(flutter.compileSdkVersion, 35)
    ndkVersion = flutter.ndkVersion
    flavorDimensions += "role"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.tripmate_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = maxOf(flutter.targetSdkVersion, 35)
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (playStoreSigningReady) {
            create("playStore") {
                storeFile = file(signingValue("storeFile"))
                storePassword = signingValue("storePassword")
                keyAlias = signingValue("keyAlias")
                keyPassword = signingValue("keyPassword")
            }
        }
    }

    productFlavors {
        create("driver") {
            dimension = "role"
            applicationId = "com.tripmate.driver"
            resValue("string", "app_name", "TripMate Driver")
            signingConfig = signingConfigs.getByName("debug")
        }
        create("transporter") {
            dimension = "role"
            applicationId = "com.tripmate.transporter"
            resValue("string", "app_name", "TripMate Transporter")
            signingConfig = signingConfigs.getByName("debug")
        }
        create("driverPlay") {
            dimension = "role"
            applicationId = "com.tripmate.driver"
            resValue("string", "app_name", "TripMate Driver")
            if (playStoreSigningReady) {
                signingConfig = signingConfigs.getByName("playStore")
            }
        }
        create("transporterPlay") {
            dimension = "role"
            applicationId = "com.tripmate.transporter"
            resValue("string", "app_name", "TripMate Transporter")
            if (playStoreSigningReady) {
                signingConfig = signingConfigs.getByName("playStore")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
    implementation("com.google.android.gms:play-services-location:21.3.0")
}
