"""Access control for sene_chantiers.

The application uses Django's own permission system, like
`parcel_historisation`: a user may use it when they hold
`sene_chantiers.manage_dossiers`. The permission is declared on
`Chantier.Meta` and granted through a group in the admin — there is
nothing instance-specific to configure, no group name to keep in an
environment variable, and no group to create by hand on each deployment.
Superusers hold every permission by definition, so they need no special
case here either.
"""

from django.contrib.auth.decorators import login_required, permission_required

PERMISSION = "sene_chantiers.manage_dossiers"


def sene_chantiers_access_required(view_func):
    """Gate a view on SSO authentication plus the application permission.

    The two standard decorators are composed rather than reimplemented, in
    this order for a reason: an anonymous visitor is sent to SSO login,
    where they can do something about it, while an authenticated user
    without the permission gets a 403 instead of a redirect they could
    never satisfy.
    """
    return login_required(
        permission_required(PERMISSION, raise_exception=True)(view_func)
    )
