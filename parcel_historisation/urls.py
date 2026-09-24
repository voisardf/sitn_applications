from django.urls import include, path
from rest_framework import routers
from parcel_historisation import views

router = routers.DefaultRouter()
router.register(r'plans', views.PlanViewSet, basename='plans-list')
router.register(r'operations', views.OperationViewSet, basename='operations')
router.register(r'balance', views.BalanceViewSet, basename='balance')

urlpatterns = [
    path('api/', include(router.urls)),

    path('', views.index, name='index'),
    path('get_docs_list', views.get_docs_list, name='get_docs_list'),
    path('get_download_path', views.get_download_path, name='get_download_path'),
    path('search_plans_by_term', views.search_plans_by_term),
    path('download/<path:name>', views.file_download),
    path('submit_saisie', views.submit_saisie),
    path('submit_balance', views.submit_balance),
    path('balance_file_upload', views.balance_file_upload),
    path('load_operation', views.load_operation),
    path('liberate', views.liberate),
    path('run_control/<path:cad_no>', views.run_control),
    path('submit_control', views.submit_control)
]
