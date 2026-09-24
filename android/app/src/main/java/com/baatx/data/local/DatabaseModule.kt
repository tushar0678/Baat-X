package com.baatx.data.local

import android.content.Context
import androidx.room.Room
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): BaatXDatabase =
        Room.databaseBuilder(context, BaatXDatabase::class.java, "baatx.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun pendingCaptureDao(db: BaatXDatabase): PendingCaptureDao = db.pendingCaptureDao()

    @Provides
    fun cachedFollowUpDao(db: BaatXDatabase): CachedFollowUpDao = db.cachedFollowUpDao()

    @Provides
    fun pendingCallDao(db: BaatXDatabase): PendingCallDao = db.pendingCallDao()
}
