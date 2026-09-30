## Contexte et objectifs

EU4 est un jeu sandbox ne disposant pas de critère de point fiable pour désigner un vainqueur.

L’application permet à un organisateur de partie d’attribuer des points aux joueurs selon ses propres critères, de façon automatique (lecture des fichiers de sauvegarde) ou manuelle.

## Fonctionnement général

L’hôte de la partie dispose d’une autosave effectuée tous les ans ou tous les 6 mois de jeu (environ 3mns20 ou 1mn40).

L’autosave est parsée et le résultat est sauvegardé dans un fichier json.

Les fichiers sont lus par l’application qui en tire des métriques clés : les guerres gagnées, les statistiques et métriques des pays joués, les provinces conquises ou perdues, etc…

Les règles de scoring de la partie sont stockées dans un fichier YAML (éditable et lisible par des non-dev), le fichier répertorie des conditions et le nombre de points gagnés ou perdus si elles sont satisfaites.

L’application lit ces règles et les applique sur le fichier JSON, et stocke en base les statistiques (sous forme de gain de point lié à un évènement). Les évènements peuvent être ponctuels (victoire dans une guerre) ou calculés chaque année (premier income, première armée, etc…).

L’application fournit une interface graphique simple permettant d’afficher les scores en temps réel. Les organisateurs peuvent ajouter ou retirer des points manuellement via l’application

## Contraintes

Une sauvegarde doit être entièrement traitée avant l’arrivée de la prochaine : parsing, calcul des conditions et attribution des scores.
L’application tourne en parallèle sur le PC de l’hôte de la partie : elle doit être sobre en ressources.

## Limitations et points de vigilance

Un joueur peut changer de pays (tag) en cours de partie.

Certains événements sont uniques mais sauvegardés dans chaque fichier de sauvegarde (victoire de X sur Y dans la guerre Z), adoption d’une institution, etc… il ne faut les sauvegarder et comptabiliser qu’une fois.



