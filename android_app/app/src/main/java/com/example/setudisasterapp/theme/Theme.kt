package com.example.setudisasterapp.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF9CD5C5), onPrimary = Color(0xFF00382D),
    primaryContainer = Color(0xFF164F42), onPrimaryContainer = Color(0xFFBCF2E1),
    secondary = Color(0xFFB5CCC3), background = Color(0xFF101513),
    surface = Color(0xFF19201D), surfaceContainerLow = Color(0xFF1E2823),
    onSurface = Color(0xFFE2E9E3), onSurfaceVariant = Color(0xFFB9C6BF),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
    errorContainer = Color(0xFF4E2020), onErrorContainer = Color(0xFFFFDAD6)
)

private val LightColorScheme =
  lightColorScheme(
    primary = Color(0xFF286452), onPrimary = Color.White,
    primaryContainer = Color(0xFFD4EBDF), onPrimaryContainer = Color(0xFF123D30),
    secondary = Color(0xFF51675D), tertiary = Color(0xFF476579),
    background = Color(0xFFF6F7F2), surface = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFEDF0E8), onSurface = Color(0xFF202B25),
    onSurfaceVariant = Color(0xFF5D6B62), outline = Color(0xFF7C897F),
    error = Color(0xFFB92D32), onError = Color.White,
    errorContainer = Color(0xFFFADBD7), onErrorContainer = Color(0xFF641C20),

    /* Other default colors to override
    background = Color(0xFFFFFBFE),
    surface = Color(0xFFFFFBFE),
    onPrimary = Color.White,
    onSecondary = Color.White,
    onTertiary = Color.White,
    onBackground = Color(0xFF1C1B1F),
    onSurface = Color(0xFF1C1B1F),
    */
  )

@Composable
fun SetuDisasterAppTheme(
  darkTheme: Boolean = isSystemInDarkTheme(),
  // Dynamic color is available on Android 12+
  dynamicColor: Boolean = false,
  content: @Composable () -> Unit,
) {
  val colorScheme =
    when {
      dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
        val context = LocalContext.current
        if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
      }
      darkTheme -> DarkColorScheme
      else -> LightColorScheme
    }

  MaterialTheme(colorScheme = colorScheme, typography = Typography, content = content)
}
