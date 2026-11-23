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


class OllamaSilence(OllamaIndisponible):
    """Ollama a répondu au début puis plus rien n'est arrivé pendant le délai de silence."""


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


DELAI_SILENCE = 600.0   # 10 minutes sans RIEN recevoir (pas 10 minutes au total)


def chat_flux(adresse: str, modele: str, messages: list[dict], schema: dict | None, num_ctx: int,
              delai_silence: float = DELAI_SILENCE, sur_texte=None, max_jetons: int = 8192,
              reflexion: bool = False) -> str:
    """Une conversation en flux (POST /api/chat) ; renvoie le texte complet de la réponse.

    `format` = schéma JSON, `options.num_ctx` = taille de contexte. Le délai est celui d'UNE lecture
    sur la connexion : tant qu'Ollama envoie quelque chose, on attend ; après `delai_silence`
    secondes sans rien recevoir, on abandonne. `sur_texte(morceau)` est appelé à chaque morceau
    reçu (pour la progression). `max_jetons` borne la longueur de la réponse (options.num_predict). Bloquant : à lancer dans un fil.
    """
    base = normaliser_adresse(adresse)
    corps = {"model": modele, "messages": messages, "stream": True,
             "options": {"num_ctx": int(num_ctx), "num_predict": int(max_jetons), "temperature": 0.7}}
    if schema is not None:
        corps["format"] = schema
    if not reflexion:
        # Gemma 4, Qwen 3… « réfléchissent » d'abord (champ message.thinking) : des milliers de
        # jetons, un tour 3 fois plus long et des réponses tronquées (constaté sur thnas).
        corps["think"] = False
    req = urllib.request.Request(
        base + "/api/chat", data=json.dumps(corps).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"})
    morceaux: list[str] = []
    silence = (f"L'IA n'a plus rien envoyé depuis {delai_silence / 60:.0f} minutes."
               if delai_silence >= 60 else f"L'IA n'a plus rien envoyé depuis {delai_silence:g} s.")
    try:
        with urllib.request.urlopen(req, timeout=delai_silence) as rep:
            for ligne in rep:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    obj = json.loads(ligne)
                except ValueError:
                    raise OllamaIndisponible(f"{base} a envoyé une réponse illisible.") from None
                if not isinstance(obj, dict):
                    continue
                if obj.get("error"):
                    raise OllamaIndisponible(f"Ollama signale une erreur : {obj['error']}")
                msg = obj.get("message") or {}
                morceau = (msg.get("content") or "") if isinstance(msg, dict) else ""
                pensee = (msg.get("thinking") or "") if isinstance(msg, dict) else ""
                if pensee and sur_texte is not None:
                    sur_texte(pensee)                  # compte dans la progression, pas dans la réponse
                if morceau:
                    morceaux.append(morceau)
                    if sur_texte is not None:
                        sur_texte(morceau)
                if obj.get("done"):
                    break
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read(2000)).get("error", "")
        except (ValueError, AttributeError, OSError):
            detail = ""
        if e.code == 400 and "think" in str(detail).lower() and not reflexion:
            # vieil Ollama ou modèle qui refuse le réglage : on redemande sans lui
            return _sans_reflexion(adresse, modele, messages, schema, num_ctx, delai_silence, sur_texte, max_jetons)
        raise OllamaIndisponible(
            f"{base} répond « {e.code} »" + (f" : {detail}" if detail else "")
            + ". Le modèle choisi est-il installé sur le PC de l'IA ?") from None
    except (socket.timeout, TimeoutError):
        raise OllamaSilence(silence) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise OllamaSilence(silence) from None
        raise OllamaIndisponible(
            f"Rien ne répond à {base}. Vérifiez que le PC est allumé et qu'Ollama tourne.") from None
    except (OSError, http.client.HTTPException):
        raise OllamaIndisponible(f"La connexion avec {base} s'est interrompue.") from None
    return "".join(morceaux)


def _sans_reflexion(adresse, modele, messages, schema, num_ctx, delai_silence, sur_texte, max_jetons) -> str:
    return chat_flux(adresse, modele, messages, schema, num_ctx, delai_silence, sur_texte, max_jetons,
                     reflexion=True)
