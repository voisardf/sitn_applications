"""Tests de l'application sene_chantiers.

Lancer avec :
    python manage.py testdb                       # provisionne la base de test
    python manage.py test sene_chantiers.tests --keepdb

Organisation :

    factories.py        fabriques d'objets et chargement des données de
                        référence fictives
    fixtures/           données de référence au format (Geo)JSON, reprenant
                        la forme des tables partagées
    test_appreciation   les trois cascades confirmées, cas limites compris
    test_models         propriétés dérivées, clean() et contraintes de base
    test_satac          résolution et autocomplétion, sur de vraies lignes
    test_access         SSO plus appartenance au groupe
    test_views          récapitulatif, rapport initial, rapport de suivi
    test_security       isolation entre onglets
    test_photos         validation au dépôt et sanitisation
    test_emails         sélection des modèles, brouillon, envoi
    test_exports        PDF et Excel
    test_deadlines      seuils, sources multiples, digest

Sur les tables partagées : elles sont `managed = False`, donc leur présence
dépend de ce que `manage.py testdb` a cloné. Les tests y insèrent de vraies
lignes fictives quand la table existe, et se sautent avec un message
explicite sinon — plutôt que de passer en silence sans rien vérifier.
"""
