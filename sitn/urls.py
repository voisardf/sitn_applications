from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from allauth.account.decorators import secure_admin_login
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from sitn.router import SitnRouter
from . import views

# Enable allauth for admin
admin.autodiscover()
admin.site.login = secure_admin_login(admin.site.login)

router = SitnRouter()

router.register_app('cadastre', 'cadastre/')
router.register_app('registre_foncier', 'registre_foncier/')
router.register_app('roads', 'roads/')
router.register_app('panoview', 'panoview/')

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', router.get_api_root_view(), name='api-root'),
    path('cadastre/', include('cadastre.urls')),
    path('registre_foncier/', include('registre_foncier.urls')),
    path('roads/', include('roads.urls')),
    path('panoview/', include('panoview.urls')),
    path("test-auth/", views.index, name="index"),
]

if settings.IS_INTRANET:
    router.register_app('ecap_intra', 'ecap/')
    router.register_app('cats', 'cats/')
    router.register_app('parcel_historisation', 'parcel_historisation/')
    router.register_app('intranet_proxy', 'intranet_proxy/')
    urlpatterns.extend([
        path('ecap/', include('ecap_intra.urls')),
        path('cats/', include('cats.urls')),
        path('parcel_historisation/', include('parcel_historisation.urls')),
        re_path(r'(?:vcron|intranet)_proxy/', include('intranet_proxy.urls')),
    ])
else:
    router.register_app('ecap', 'ecap/')
    router.register_app('action_sociale', 'action_sociale/')
    router.register_app('health', 'health/')
    router.register_app('stationnement', 'stationnement/')
    router.register_app('forest_forpriv', 'forest_forpriv/')
    urlpatterns.extend([
        path('ecap/', include('ecap.urls')),
        path('action_sociale/', include('action_sociale.urls')),
        path('health/', include('health.urls')),
        path("ppe/", include("ppe.urls")),
        path('stationnement/', include('stationnement.urls')),
        path('forest_forpriv/', include('forest_forpriv.urls')),
    ])
