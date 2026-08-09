# invoice-repo
print("bonjour à tous")


nouvelle mise a jour :
desormais si tu fait une modification qui t'amene a installer de nouvelles librairies,

tu doit taper la commande pip freeze > requirements.txt

cette commandes te permet de recuperer la liste des librairies requises pour le bon fonctionnement du site.

ce n'est qu'apres cette commande que tu doit envoyer ta modification sur github.


la personne qui es censée recevoir le code

tapera la commande pip install -r requirements.txt pour metre a jour ces librairies avant de demarer le serveur.

attention avant chacune de ces comandes , il faut s'assurer que l'environnement virtuel est activé
