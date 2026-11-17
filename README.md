# Dikevia — démonstrateur du chatbot juridique

Ce dépôt contient le kit de démonstration du chatbot Dikevia, son image Docker et une protection d'accès HTTP Basic.

> **Statut : démonstrateur technique.** La réussite du build Docker et des tests automatisés ne constitue pas une validation juridique, un audit de sécurité complet ou une autorisation de mise en production commerciale. Le kit d'origine est un environnement de développement local.

## Contenu

- `Dikevia_Chatbot_V1_Kit_Developpeur (1).zip` : kit applicatif.
- `Dockerfile` : construction de l'image.
- `secure_main.py` : barrière d'authentification des routes applicatives et route de santé Render minimale.
- `render.yaml` : configuration Render (Docker, région de Francfort, plan gratuit pour le démonstrateur, secrets demandés à la création, déploiement après réussite des contrôles GitHub).
- `.github/workflows/validate-demo.yml` : tests automatiques de construction, de démarrage et de contrôle d'accès.

## Variables d'environnement obligatoires

Le serveur refuse de démarrer si ces deux variables ne sont pas configurées :

- `DIKEVIA_DEMO_USER` : au moins 3 caractères.
- `DIKEVIA_DEMO_PASSWORD` : au moins 24 caractères.

**Ne placez jamais leurs valeurs dans le dépôt, dans le Dockerfile, dans le code source ou dans un message public.** Configurez-les uniquement dans les variables/secrets de l'hébergeur.

## Essai local

Après avoir construit l'image :

```bash
docker build -t dikevia-chatbot-demo .
docker run --rm -p 8000:8000 \
  -e DIKEVIA_DEMO_USER=demo-user \
  -e DIKEVIA_DEMO_PASSWORD='REMPLACER_PAR_UN_SECRET_DE_24_CARACTERES_MINIMUM' \
  dikevia-chatbot-demo
```

Puis ouvrir `http://127.0.0.1:8000/health` et saisir les identifiants de démonstration dans la fenêtre d'authentification du navigateur.

Cet exemple est destiné à un essai local uniquement. Ne réutilisez pas les valeurs d'exemple comme identifiants réels.

## Hébergement

- Activer HTTPS/TLS avant toute exposition sur Internet : HTTP Basic transmet les identifiants encodés, pas chiffrés.
- Définir les deux variables dans le gestionnaire de secrets de l'hébergeur.
- Ne jamais désactiver la barrière d'authentification pour rendre le chatbot public.
- Prévoir avant toute ouverture à des utilisateurs : limitation de débit, surveillance des abus, gestion des coûts, politique de conservation des données, tests de sécurité et validation juridique des réponses.
- La route `/_render-health` répond publiquement `200` avec le seul texte `ok` pour les contrôles de disponibilité Render ; elle ne donne accès à aucune route applicative.
- La route applicative `/health` reste protégée par authentification, comme le reste du chatbot.

## Validation continue

À chaque modification de la branche `main`, GitHub Actions :

1. construit l'image Docker ;
2. vérifie que l'application refuse de démarrer sans secrets ;
3. démarre le conteneur avec des identifiants temporaires de CI ;
4. vérifie que les bons identifiants sont acceptés ;
5. vérifie que la route de santé Render répond `200` sans identifiants ;
6. vérifie que l'accès anonyme et un mauvais mot de passe sont refusés.

Les identifiants utilisés par la CI sont temporaires et ne sont pas des secrets de production. Le workflow construit et teste l'image ; il ne la publie pas et ne déploie pas l'application. La configuration Render attend la réussite des contrôles GitHub avant tout déploiement automatique.

## Préparation Render

Le fichier `render.yaml` prépare un Blueprint Render, mais **ne crée pas à lui seul le service et ne lance aucun déploiement**. Pour le créer :

1. Connecter le compte GitHub à Render.
2. Dans Render, choisir **New → Blueprint**.
3. Sélectionner le dépôt `dikevia/Chatbot-demo` et la branche `main`.
4. Vérifier le service `dikevia-chatbot-demo` et la région Frankfurt.
5. Renseigner `DIKEVIA_DEMO_USER` (au moins 3 caractères) et `DIKEVIA_DEMO_PASSWORD` (au moins 24 caractères) dans le formulaire Render. Utiliser un mot de passe unique et ne jamais le communiquer dans le chat ou le dépôt.
6. Vérifier le coût affiché avant de confirmer la création.

Le Blueprint propose le plan gratuit pour le démonstrateur. Il convient aux essais, pas à une disponibilité commerciale garantie. Les services gratuits peuvent s'endormir après une période d'inactivité et redémarrer à la première requête. Le service est prévu pour Francfort. Render fournit le HTTPS pour son domaine `onrender.com`.

## Limites connues

- Aucune base PostgreSQL/Neon n'est configurée dans ce démonstrateur.
- Le dépôt ne produit pas encore d'application Android installable (APK).
- Les tests automatisés vérifient le conteneur et la barrière d'accès, pas la justesse des réponses juridiques ni l'intégralité du parcours utilisateur.
