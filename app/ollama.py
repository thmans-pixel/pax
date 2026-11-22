"""Parler à l'Ollama du PC. Uniquement la bibliothèque standard (pas de dépendance)."""
from __future__ import annotations

import http.client
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


class OllamaIndisponible(Exception):
    """L'Ollama ne répond pas ; le message dit quoi vérifier."""


def normaliser_adresse(adresse: str) -> str:
    """http://hote:11434 sans « / » final. Refuse tout ce qui n'est pas http(s)."""
    a = (adresse or "").strip()
    if not a:
        raise ValueError("adresse vide")
    if "://" not in a:
        a = "http://" + a
    p = urllib.parse.urlsplit(a)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("l'adresse doit commencer par http:// ou https://")
    if p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise ValueError("l'adresse doit être simple, par exemple http://192.168.1.20:11434")
    try:
        p.port
    except ValueError:
        raise ValueError("le numéro de port est invalide") from None
    return f"{p.scheme}://{p.netloc}"


def lister_modeles(adresse: str, delai: float = 5.0) -> list[str]:
    """Noms des modèles installés (GET /api/tags). Lève OllamaIndisponible avec un conseil."""
    base = normaliser_adresse(adresse)
    req = urllib.request.Request(base + "/api/tags", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=delai) as rep:
            corps = rep.read(2_000_000)
    except urllib.error.HTTPError as e:
        raise OllamaIndisponible(
            f"{base} répond « {e.code} » : ce n'est pas un Ollama, ou un proxy s'interpose.") from None
    except (socket.timeout, TimeoutError):
        raise OllamaIndisponible(
            f"Pas de réponse de {base} au bout de {delai:g} s. Le PC est peut-être éteint, "
            "ou son pare-feu bloque le port d'Ollama (11434).") from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise OllamaIndisponible(
                f"Pas de réponse de {base} au bout de {delai:g} s. Le PC est peut-être éteint, "
                "ou son pare-feu bloque le port d'Ollama (11434).") from None
        raise OllamaIndisponible(
            f"Rien ne répond à {base}. Vérifiez que le PC est allumé, qu'Ollama tourne et "
            "qu'il écoute sur le réseau local (OLLAMA_HOST=0.0.0.0).") from None
    except (OSError, http.client.HTTPException):
        raise OllamaIndisponible(f"{base} ne répond pas comme un Ollama (mauvais port ?).") from None
    try:
        modeles = json.loads(corps)["models"]
        return sorted(m["name"] for m in modeles)
    except (ValueError, KeyError, TypeError):
        raise OllamaIndisponible(
            f"{base} a répondu, mais ce n'est pas la réponse d'un Ollama. Vérifiez l'adresse.") from None
