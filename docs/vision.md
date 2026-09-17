# VISION : document de produit, pas le contrat d'API

Ce fichier décrit la cible à long terme. L'API et le comportement réels
sont ceux du README et du package `jev-agent-router` 0.1.x.

# JEV Agent Router

Couche de décision entre une tâche et un registre d'agents.

Le routeur répond uniquement à :

> Parmi ces agents déclarés, lequel peut traiter cette tâche maintenant,
> avec quelles justifications, ou faut-il s'abstenir ?

Il ne doit pas exécuter l'agent, ni lui fournir des outils, ni élargir
ses permissions.

## Pipeline cible

```text
Tâche
  → contraintes d'accès (scope, permissions)
  → candidats du registre
  → jugement (local ou JEV)
  → select | fallback | abstain
  → runtime externe, hors de ce paquet
```

## Principes

- Les permissions viennent du registre et de l'appelant.
- Aucune entrée issue d'un modèle, document ou outil n'accorde de droit.
- Le repli est borné à un saut et repasse les mêmes filtres.
- L'abstention est une décision valide.
- Les traces n'enregistrent pas de secret.

## Providers

- `local` : heuristique déterministe, hors réseau.
- `mock` : démo et CI.
- `custom` : endpoint fourni par l'utilisateur.
- `jev` : jugement JEV plus gateway OpenAI-compatible.

## Hors périmètre

Ce composant n'est pas un orchestrateur, pas un runtime, et pas un
security-gate. Il sélectionne. L'exécution et ALLOW / ASK / DENY restent
ailleurs dans JEV Labs.
