import requests, logging, re, datetime
from functools import wraps

from .forms import GeolocalisationForm
from .models import DossierPPE, GeoshopCadastreOrder
from django.shortcuts import render, redirect
from django.http import HttpResponseBadRequest, Http404

logger = logging.getLogger(__name__)

# BOUNDING BOX CANTON NEUCHATEL
NE_MIN_EST = 2515000
NE_MAX_EST = 2585000
NE_MIN_NORD = 1180000
NE_MAX_NORD = 1230000

# Geolocalisation service
GEOLOC_SERVICE_URL = 'https://sitn.ne.ch/satac_localisation?'

# REGEXP FOR GEOSHOP ORDER
GEOSHOP_ORDER_REGEX = re.compile(r'(\d{8})_(\d{5,7})')


def login_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if 'login_code' in request.session : 
            logger.debug('== Trying to log in with code')
            try:
                return func(request, DossierPPE.objects.get(login_code=request.session['login_code']), *args, **kwargs)
            except Http404 as e:
                raise Http404('File not found.')
            except Exception as e:
                logger.warning(f"Exception : {repr(e)}")
                pass
        return redirect('ppe:login')
    return wrapper

def get_localisation(request, localisation):

    try:
        coords = localisation['coordinates']
        coord_est = round(coords[0],1)
        coord_nord = round(coords[1],1)
    except KeyError:
        return render(request,
            "ppe/geolocalisation.html",
            {
                "error_message": "Les coordonnées n'ont pas pu être récupérées.",
                "form": GeolocalisationForm
            },
        )

    if (NE_MIN_EST < coord_est < NE_MAX_EST) and (NE_MIN_NORD < coord_nord < NE_MAX_NORD):
        url = GEOLOC_SERVICE_URL+"X="+str(coord_est)+"&Y="+str(coord_nord)

        headers = {
            'cache-control': "no-cache",
            'postman-token': "c71c65a6-07f4-a2a4-a6f8-dca3fd706a7a"
            }

        response = requests.request("GET", url, headers=headers)
        data = response.json()
        
        # THERE MIGHT BE DDP's ...
        if isinstance(data, dict) and 'bien_fonds' in data:
            if isinstance(data['bien_fonds'], list):
                bf = None
                bf_list = []
                for i in range(len(data['nummai'])):
                    for k,v in data['bien_fonds'][i].items():
                        bf_type = k
                    bf_list.append({
                        "bf_type" : bf_type,
                        "nummai" : data["nummai"][i]
                    })
            else:
                bf_list = None
                bf = {
                "bf_type" : 'bien_fonds',
                "nummai" : data["nummai"]
                }
            numcad = data["numcad"]
            cadastre = data["nomcad"]
        else:
            return HttpResponseBadRequest("Une erreur inconnue s'est produite. La localisation a échouée.")

    else:
        return HttpResponseBadRequest("La localisation semble se situer en dehors du canton.")

    geoloc = {
        "egrid": "ToDo",
        "bf_list": bf_list,
        "bien_fonds": bf,
        "numcad": numcad,
        "cadastre": cadastre,
        "coord_est": coord_est,
        "coord_nord": coord_nord,
        "coordinates": coords
    }

    return(geoloc)

def check_geoshop_ref(ref, doc):
    """ Validation of the provided geoshop reference:
        Does an order with the provided id exist where
        the PPE coordinates lay within the order perimeter
        and where the reference date is in the interval
        date_ordered - date_processed and the order_date 
        not older than a year
    """
    current = datetime.date.today()
    check_date = current-datetime.timedelta(days=365)
    pt_geom = doc.geom

    # Change representation of PPE geolocalisation point
    if ref is None:
        return False, 'La référence de commande indiquée est vide ou n\'existe pas.'
    logger.info('CHECKING geoshop reference: %s', ref)

    # Check if the given reference respects the supposed format
    if GEOSHOP_ORDER_REGEX.search(ref):
        order_date, order_ref = ref.split('_')  
        order_date = datetime.datetime.strptime(order_date, '%Y%m%d').date()
        logger.info("date_commande: %s et no_ref: %s", order_date, order_ref)
    else:
        logger.info('Geoshop reference: %s does not exist', ref)
        return False, 'La référence de commande indiquée n\'existe pas.'

    # Check if the given order date is more recent than a year
    if order_date < check_date:
        return False, 'Les données ont plus d\'une année, merci de commander de nouvelles données.'

    # Check if the order date has not been invented or misspelled, thus laying in the future
    if current < order_date:
        return False, 'La date de commande référencée se situe dans le futur.'
    
    # The order date and ref structure are plausible, so we check in the database validating
    # that the order_id exists and the selected real estate is within the order perimeter
    geoshop_order = GeoshopCadastreOrder.objects.filter(pk=int(order_ref), geom__contains=pt_geom).first()

    # Check if there is a result and both order and processing date exist
    if not geoshop_order:
        return False, f"Les données commandées ne comprennent pas le bien-fonds {doc.nummai} du cadastre de {doc.cadastre}."
    # Check if the result has an existing order date
    if geoshop_order.date_ordered == '' or geoshop_order.date_ordered is None:
        return False, 'La commande référencée n\'a pas de date de commande valide.'
    # Check if the result has an existing processing date
    if geoshop_order.date_processed == '' or geoshop_order.date_processed is None:
        return False, 'La commande référencée n\'a pas de date de traitement valide.'
    # Check if the given reference date lays in the interval between order and processing date 
    if geoshop_order.date_ordered.date() <= order_date <= geoshop_order.date_processed.date():
        return True, None
    else:
        return False, 'La date de commande de la référence semble erronée.'

def check_alerts(dossier_ref):

    # Alert 1: There is a abandoned dossier with the same cadastre, property and type
    dossier_list = DossierPPE.objects.get(cadastre=dossier_ref.cadastre)

    return