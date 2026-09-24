package com.baatx.data.repository

import com.baatx.domain.repository.*
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds @Singleton
    abstract fun authRepository(impl: AuthRepositoryImpl): AuthRepository

    @Binds @Singleton
    abstract fun conversationRepository(impl: ConversationRepositoryImpl): ConversationRepository

    @Binds @Singleton
    abstract fun customerRepository(impl: CustomerRepositoryImpl): CustomerRepository

    @Binds @Singleton
    abstract fun leadRepository(impl: LeadRepositoryImpl): LeadRepository

    @Binds @Singleton
    abstract fun followUpRepository(impl: FollowUpRepositoryImpl): FollowUpRepository

    @Binds @Singleton
    abstract fun reportRepository(impl: ReportRepositoryImpl): ReportRepository

    @Binds @Singleton
    abstract fun assistantRepository(impl: AssistantRepositoryImpl): AssistantRepository

    @Binds @Singleton
    abstract fun whatsAppRepository(impl: WhatsAppRepositoryImpl): WhatsAppRepository
}
