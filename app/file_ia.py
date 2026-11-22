"""La file d'attente unique vers Ollama : une seule demande à la fois, dans l'ordre d'arrivée.

La carte graphique du PC est partagée ; deux demandes en même temps ne feraient que se ralentir.
Fils d'exécution classiques (threading) : la file ne dépend pas de la boucle asynchrone.
"""
from __future__ import annotations

import threading


class FileIA:
    def __init__(self):
        self._cond = threading.Condition()
        self._tickets: list[object] = []

    def prendre(self) -> object:
        """Se met en file ; à appeler dans l'ordre où les demandes arrivent."""
        t = object()
        with self._cond:
            self._tickets.append(t)
        return t

    def devant(self, t: object) -> int:
        """Nombre de demandes qui passent avant celle-ci (0 = c'est son tour)."""
        with self._cond:
            try:
                return self._tickets.index(t)
            except ValueError:
                return 0

    def attendre(self, t: object, abandon: threading.Event | None = None, pas: float = 0.1) -> bool:
        """Bloque jusqu'au tour de `t`. Renvoie False si on abandonne avant."""
        with self._cond:
            while self._tickets and self._tickets[0] is not t:
                if abandon is not None and abandon.is_set():
                    return False
                self._cond.wait(pas)
            return True

    def liberer(self, t: object) -> None:
        with self._cond:
            try:
                self._tickets.remove(t)
            except ValueError:
                pass
            self._cond.notify_all()

    def taille(self) -> int:
        with self._cond:
            return len(self._tickets)
