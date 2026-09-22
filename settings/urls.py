from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('auth.urls')),
    path('api/clients/', include('client.urls')),
    path('api/account/', include('account.urls')),
    path('api/questions/', include('question.urls')),
    path('api/chat/', include('message.urls')),
    path('api/video/', include('video.urls')),
    path('api/courses/', include('course.urls')),
    path('api/assessments/', include('assessment.urls')),
    path('api/certificates/', include('certificate.urls')),
    path('api/earnings/', include('earning.urls')),
    path('api/notifications/', include('notification.urls')),
    path('api/payments/', include('payment.urls')),
    path('api/transactions/', include('transaction.urls')),
    path('api/analytics/', include('analytic.urls')),
    path('api/blog/', include('blog.urls')),
]