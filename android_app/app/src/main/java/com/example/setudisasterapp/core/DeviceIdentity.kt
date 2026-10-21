package com.example.setudisasterapp.core

import android.content.Context
import java.util.UUID

object DeviceIdentity {
    fun id(context: Context): String {
        val preferences = context.getSharedPreferences("setu_identity", Context.MODE_PRIVATE)
        val existing = preferences.getString("device_id", null)
        if (existing != null) return existing
        val generated = UUID.randomUUID().toString()
        preferences.edit().putString("device_id", generated).apply()
        return generated
    }
}
