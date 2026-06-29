from django.contrib import admin
from django_extended_ol.admin import WMTSGISModelAdmin

from .models import DossierPPE, AdresseFacturation, ContactPrincipal, Notaire, Signataire, Geolocalisation, Zipfile


class ZipfileInline(admin.TabularInline):
     model = Zipfile

class DossierPPEAdmin(WMTSGISModelAdmin):
    search_fields = [
        'nummai',
        'cadastre',
        'contact_principal',
        'login_code',
        'statut',
        'type_dossier',
        'date_creation'
    ]
    list_filter = [
        'statut', 
        'type_dossier',
        'date_creation'
    ]
    list_display = [
        'id',
        'cadastre',
        'nummai',
        'contact_principal',
        'type_dossier',
        'ref_dossier_initial',
        'statut',
        'latest_zipfile_statut',
        'date_creation',
        'aff_infolica'
    ]
    inlines = [
         ZipfileInline
    ]

    def latest_zipfile_statut(self, obj):
            latest_zip = obj.zipfiles.order_by('-upload_date').first()
            return latest_zip.get_file_statut_display() if latest_zip else "—"

    latest_zipfile_statut.short_description = "Dernier statut ZIP"

class ContactPrincipalAdmin(admin.ModelAdmin):
    search_fields= [
         'nom',
         'prenom',
         'email'
    ]
    list_display = [
        'id',
        'nom',
        'prenom',
        'raison_sociale',
        'email',
        'no_tel'
    ]

class ZipfileAdmin(admin.ModelAdmin):
    search_fields = [
        'dossier_ppe'
    ]
    list_filter = [
        'dossier_ppe',
        'file_statut', 
        'upload_date'
    ]
    list_display = [
        'id',
        'dossier_ppe_id',
        'dossier_ppe_cadastre',
        'dossier_ppe_nummai',
        'dossier_ppe_type_dossier',
        'file_statut',
        'zipfile',
        'upload_date'
    ]
    def dossier_ppe_id(self, obj):
        return obj.dossier_ppe.id

    def dossier_ppe_cadastre(self, obj):
        return obj.dossier_ppe.cadastre

    def dossier_ppe_nummai(self, obj):
        return obj.dossier_ppe.nummai

    def dossier_ppe_type_dossier(self, obj):
        return obj.dossier_ppe.get_type_dossier_display()

    dossier_ppe_id.short_description = "Dossier PPE"
    dossier_ppe_cadastre.short_description = "Cadastre"
    dossier_ppe_nummai.short_description = "Nummai"


class NotaireAdmin(admin.ModelAdmin):
    search_fields= [
         'nom',
         'prenom',
         'complement'
    ]
    list_display = [
        'nom',
        'prenom',
        'complement',
        'rue',
        'no_rue',
        'npa',
        'localite'
    ]

admin.site.register(AdresseFacturation)
admin.site.register(ContactPrincipal, ContactPrincipalAdmin)
admin.site.register(DossierPPE, DossierPPEAdmin)
admin.site.register(Notaire, NotaireAdmin)
admin.site.register(Signataire)
admin.site.register(Zipfile, ZipfileAdmin)
