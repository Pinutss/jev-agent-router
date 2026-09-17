"""Point d'extension interne pour un juge externe.

Ce protocole n'est pas exporté. HeuristicRouter et les providers
JEV / gateway couvrent le classement public.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import AgentProfile, RouteRequest


class Judge(Protocol):
    """Réordonne des candidats déjà filtrés et valides.

    Contrat attendu : sortie déterministe pour une entrée donnée, aucun
    effet de bord, aucune élévation de permissions. Un juge ne peut pas
    réintroduire un agent rejeté par les règles d'accès.
    """

    def rerank(
        self,
        request: RouteRequest,
        candidates: Sequence[AgentProfile],
    ) -> Sequence[tuple[AgentProfile, float, tuple[str, ...]]]:
        """Retourne les candidats ordonnés, avec score et justification."""
        ...
