"""Template context shared across sene_chantiers views."""

from .auth import user_is_sene_chantiers_admin
from .services import deadlines


def deadline_banner(request):
    """Counts for the deadline banner, for authorised users only.

    Computed on read rather than stored, so it can never fall out of step
    with the measures themselves.
    """
    # Ask the resolver which app served this request rather than matching
    # the path. The deployed instances run under a script prefix (ROOTURL
    # -> FORCE_SCRIPT_NAME), so request.path reads
    # "/apps_inter/sene_chantiers/..." there and a startswith() check on
    # "/sene_chantiers/" silently hides the banner everywhere but a
    # developer machine.
    match = getattr(request, "resolver_match", None)
    if match is None or match.app_name != "sene_chantiers":
        return {}
    if not user_is_sene_chantiers_admin(getattr(request, "user", None)):
        return {}
    counts = deadlines.banner_counts()
    return {
        "sc_overdue_count": counts["overdue"],
        "sc_due_soon_count": counts["due_soon"],
        "sc_pending_closure_count": counts["pending_closure"],
    }
