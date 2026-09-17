"""Erreurs publiques du routeur."""


class RouterError(Exception):
    """Erreur de base du routeur."""


class ConfigurationError(RouterError):
    """Configuration manquante ou invalide."""


class ProviderError(RouterError):
    """Échec d'un provider distant."""
