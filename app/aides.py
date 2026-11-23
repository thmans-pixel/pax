"""Les aides de l'IA : rapport de situation, conseiller, dirigeants (diplomatie).

Règle d'or (« qui sait quoi ») : ces trois aides ne voient que ce que le JOUEUR a le droit de savoir.
- événements : seulement `evenements_visibles()` (publics, ou secrets qui impliquent sa nation) ;
- JAMAIS `histoire[].resume`, `faits_etablis`, `corrections`, `scenario.contexte` ni `scenario.regles` :
  le narrateur les écrit ou les lit sans filtre de secret ; seul le narrateur les voit ;
- un dirigeant ne reçoit que les événements publics (ou secrets partagés avec le joueur et lui-même),
  sa propre nation, sa relation avec le joueur et SA conversation (20 derniers messages) ;
- une conférence (plusieurs dirigeants) : événements publics, ou secrets connus du joueur ET de TOUS les
  invités (intersection), et la transcription de la conférence seule, jamais les conversations à deux.
Aucun identifiant de joueur (compte YunoHost) n'entre dans une requête.
"""
from __future__ import annotations

from .monde import (LIBELLES_CHIFFRES, CHIFFRES, cle_relation, date_fr, est_disparue, evenements_visibles,
                    guerres_de, palier, relations_de)
from .tour import (ContexteTropPetit, LONGUEUR_ORDRE, RESERVE_REPONSE, _ligne_nation, _liste_textes, _en_vue,
                   estimer_jetons, lire_reponse)

GENRES = ("rapport", "conseiller", "diplomatie", "conference")
MAX_CONFERENCE = 5           # nations invitées à une conférence
LONGUEUR_REPONSE_CONF = 600  # la réponse d'un dirigeant en conférence
LONGUEUR_MESSAGE = 1000      # un message du joueur
MESSAGES_ENVOYES = 20        # derniers messages d'une conversation envoyés à l'IA
MESSAGES_GARDES = 60         # derniers messages d'une conversation gardés dans la sauvegarde
LONGUEUR_REPONSE = 3000
SUGGESTIONS = 3


# ------------------------------------------------------------------ schémas (toutes les clés obligatoires)
def schema_rapport() -> dict:
    texte = {"type": "string"}
    liste = {"type": "array", "items": texte}
    return {"type": "object",
            "properties": {"situation": texte, "menaces": liste, "occasions": liste, "suggestions": liste},
            "required": ["situation", "menaces", "occasions", "suggestions"]}


def schema_reponse() -> dict:
    return {"type": "object", "properties": {"reponse": {"type": "string"}}, "required": ["reponse"]}


def schema_conference(ids: list[str]) -> dict:
    """Une entrée par dirigeant invité ; toutes les clés obligatoires (sortie contrainte d'Ollama)."""
    entree = {"type": "object",
              "properties": {"nation": {"type": "string", "enum": list(ids)}, "texte": {"type": "string"}},
              "required": ["nation", "texte"]}
    return {"type": "object", "properties": {"reponses": {"type": "array", "items": entree}},
            "required": ["reponses"]}


# ------------------------------------------------------------------ consignes
CONSIGNE_RAPPORT = """\
Tu es l'état-major d'un jeu de stratégie au tour par tour. Tu rédiges, en français, le rapport de \
situation de la nation du joueur à partir de ce qu'elle sait (ci-dessous) et de rien d'autre.
Réponds UNIQUEMENT par un objet JSON avec ces clés, toutes obligatoires :
- « situation » : la situation en quelques lignes (3 à 5 phrases) ;
- « menaces » : une liste de 2 à 4 menaces, une phrase chacune ;
- « occasions » : une liste de 2 à 4 occasions à saisir, une phrase chacune ;
- « suggestions » : exactement 3 ordres que le joueur pourrait donner, écrits à l'impératif, \
concrets, d'une phrase (ex. « Proposer une alliance défensive à la Belgique »).
N'invente aucun fait absent des données. N'écris jamais de texte hors du JSON.
"""

CONSIGNE_CONSEILLER = """\
Tu es le conseiller du dirigeant d'une nation dans un jeu de stratégie au tour par tour. Tu réponds en \
français, avec franchise, en t'appuyant sur l'état de la nation, ce qu'elle sait du monde et l'objectif \
du joueur (ci-dessous), et sur rien d'autre : si tu ne sais pas, dis-le. Réponse courte (quelques \
phrases), avec des conseils concrets quand c'est utile. Tu ne décides pas à la place du joueur.
Réponds UNIQUEMENT par un objet JSON {"reponse": "…"} sans texte autour.
"""


def consigne_dirigeant(nom_nation: str, dirigeant: str) -> str:
    qui = f"{dirigeant}, dirigeant de {nom_nation}" if dirigeant else f"le dirigeant de {nom_nation}"
    return f"""\
Tu incarnes {qui}, dans un jeu de stratégie au tour par tour. Le joueur, qui dirige une autre nation, \
discute avec toi. Réponds en français, à la première personne, dans le ton de ton régime et de ton \
époque, en quelques phrases. Tu défends les intérêts de ta nation : tu peux accepter, refuser, marchander \
ou menacer, selon ta relation avec le joueur et ta situation. Tu ne sais que ce qui figure ci-dessous : \
n'invente ni secret ni fait précis qui n'y figure pas. Ce qui est dit ici ne change rien tout de suite : \
l'histoire en tiendra compte au prochain tour.
Réponds UNIQUEMENT par un objet JSON {{"reponse": "…"}} sans texte autour.
"""


def consigne_conference(invites: list[tuple[str, str, str]]) -> str:
    """`invites` : (id, nom de la nation, dirigeant) dans l'ordre de parole."""
    liste = "\n".join(f"- [{i}] {nom}" + (f", dirigeant : {d}" if d else "") for i, nom, d in invites)
    return f"""\
Tu fais parler, dans un jeu de stratégie au tour par tour, les dirigeants réunis autour d'une même table avec \
le joueur, qui dirige une autre nation :
{liste}
Chacun répond au dernier message du joueur à son tour, dans l'ordre ci-dessus, en français, à la première \
personne, dans le ton de son régime et de son époque, en 1 à 3 phrases. Il tient compte de ce que les dirigeants \
précédents viennent de dire (accord, désaccord, surenchère) et défend les intérêts de SA nation. Chaque dirigeant \
ne parle que pour lui. Ne sais que ce qui figure ci-dessous : n'invente ni secret ni fait précis absent. Ce qui est \
dit ici ne change rien tout de suite : l'histoire en tiendra compte au prochain tour.
Réponds UNIQUEMENT par un objet JSON {{"reponses": [{{"nation": "<id entre crochets>", "texte": "…"}}, …]}}, \
exactement une entrée par dirigeant, dans l'ordre, sans texte autour.
"""


# ------------------------------------------------------------------ ce que les aides ont le droit de voir
def _ev(e: dict, etat: dict) -> str:
    noms = ", ".join(etat["nations"][p]["nom"] for p in e.get("pays", []) if p in etat["nations"])
    texte = " ".join(str(e.get("texte", "")).split())
    if len(texte) > 300:
        texte = texte[:299] + "…"
    return f"- {date_fr(e['date'])} : {e['titre']}" + (f" ({noms})" if noms else "") + (f" — {texte}" if texte else "")


def _guerres(etat: dict) -> list[str]:
    nom = lambda ids: ", ".join(etat["nations"][i]["nom"] for i in ids if i in etat["nations"])
    return [f"- {g['nom']} : {nom(g['camp_a'])} contre {nom(g['camp_b'])}" for g in etat["guerres"]] or ["(aucune)"]


def contexte_joueur(etat: dict, noms_terr: dict[str, str], nb_evenements: int) -> list[str]:
    """Ce que la nation du joueur sait : sa fiche, les fiches publiques des puissances en vue,
    ses relations, les guerres, les événements visibles. Pas d'histoire, pas de faits établis."""
    j = etat["nation_joueur"]
    L = [f"Date : {date_fr(etat['date'])}. Tour {etat['tour']}.",
         f"Le monde : {etat['scenario']['nom']} — {' '.join(str(etat['scenario'].get('description', '')).split())}",
         "", "## La nation du joueur", _ligne_nation(etat, j, noms_terr, True)]
    n = etat["nations"][j]
    L.append("Évolution depuis le début : " + ", ".join(
        f"{LIBELLES_CHIFFRES[c]} {n[c] - n['depart'][c]:+d}" for c in CHIFFRES))
    if etat.get("objectif"):
        L += ["", "## Objectif du joueur", etat["objectif"]]
    L += ["", "## Ses relations"]
    rel = relations_de(etat, j)
    L += [f"- {p} : " + ", ".join(f"{r['nom']} ({r['note']:+d})" for r in rel[p]) for p in rel] or ["(aucune connue)"]
    L += ["", "## Guerres dans le monde"] + _guerres(etat)
    vue = _en_vue(etat)
    L += ["", "## Puissances en vue"] + ([_ligne_nation(etat, v, noms_terr, True) for v in vue] or ["(aucune)"])
    dernier = etat.get("dernier_tour")
    if dernier:
        L += ["", f"## Issue de vos ordres au dernier tour (tour {dernier['tour']})"]
        L += [f"- {i['ordre']} → {i.get('issue') or 'non précisé'}" for i in dernier.get("issues", [])]
    visibles = evenements_visibles(etat)
    L += ["", "## Événements connus (les plus récents en dernier)"]
    L += [_ev(e, etat) for e in visibles[len(visibles) - min(nb_evenements, len(visibles)):]] or ["(aucun)"]
    return L


def evenements_pour_dirigeant(etat: dict, nid: str) -> list[dict]:
    """Événements publics, plus les secrets que partagent le joueur ET ce dirigeant."""
    return [e for e in evenements_visibles(etat) if not e.get("secret") or nid in e.get("pays", [])]


def contexte_dirigeant(etat: dict, nid: str, noms_terr: dict[str, str], nb_evenements: int) -> list[str]:
    j = etat["nation_joueur"]
    note = etat["relations"].get(cle_relation(nid, j), 0)
    en_guerre = any((nid in g["camp_a"] and j in g["camp_b"]) or (nid in g["camp_b"] and j in g["camp_a"])
                    for g in etat["guerres"])
    moi, lui = etat["nations"][nid], etat["nations"][j]
    L = [f"Date : {date_fr(etat['date'])}.",
         "", "## Ta nation", _ligne_nation(etat, nid, noms_terr, True),
         "", "## Ton interlocuteur",
         f"Le dirigeant de {lui['nom']}" + (f" ({lui['dirigeant']})" if lui["dirigeant"] else "")
         + f", régime : {lui['regime'] or 'inconnu'}.",
         f"Ta relation avec {lui['nom']} : {note:+d} ({palier(note)})" + (", vous êtes EN GUERRE." if en_guerre else "."),
         "", "## Tes guerres"]
    mes = guerres_de(etat, nid)
    L += [f"- {g['nom']} : {', '.join(g['camp_a'])} contre {', '.join(g['camp_b'])}" for g in mes] or ["(aucune)"]
    evs = evenements_pour_dirigeant(etat, nid)
    L += ["", "## Événements publics récents"]
    L += [_ev(e, etat) for e in evs[len(evs) - min(nb_evenements, len(evs)):]] or ["(aucun)"]
    return L


def evenements_pour_conference(etat: dict, ids: list[str]) -> list[dict]:
    """Événements publics, plus les secrets connus du joueur ET de tous les invités (intersection)."""
    return [e for e in evenements_visibles(etat)
            if not e.get("secret") or all(i in e.get("pays", []) for i in ids)]


def contexte_conference(etat: dict, ids: list[str], noms_terr: dict[str, str], nb_evenements: int) -> list[str]:
    j = etat["nation_joueur"]
    lui = etat["nations"][j]
    L = [f"Date : {date_fr(etat['date'])}.", "", "## Les dirigeants invités"]
    L += [_ligne_nation(etat, i, noms_terr, True) for i in ids]
    L += ["", "## Le joueur (autre nation)",
          f"Le dirigeant de {lui['nom']}" + (f" ({lui['dirigeant']})" if lui["dirigeant"] else "")
          + f", régime : {lui['regime'] or 'inconnu'}.", "", "## Relations"]
    nom = lambda i: etat["nations"][i]["nom"]
    rel = []
    for i in ids:
        note = etat["relations"].get(cle_relation(i, j), 0)
        rel.append(f"- {nom(i)} avec {lui['nom']} : {note:+d} ({palier(note)})")
    for k, a_ in enumerate(ids):
        for b_ in ids[k + 1:]:
            note = etat["relations"].get(cle_relation(a_, b_), 0)
            rel.append(f"- {nom(a_)} avec {nom(b_)} : {note:+d} ({palier(note)})")
    L += rel
    L += ["", "## Leurs guerres"]
    vues, guerres = set(), []
    for i in ids:
        for g in guerres_de(etat, i):
            if g["nom"] not in vues:
                vues.add(g["nom"])
                guerres.append(f"- {g['nom']} : {', '.join(g['camp_a'])} contre {', '.join(g['camp_b'])}")
    L += guerres or ["(aucune)"]
    evs = evenements_pour_conference(etat, ids)
    L += ["", "## Événements publics récents"]
    L += [_ev(e, etat) for e in evs[len(evs) - min(nb_evenements, len(evs)):]] or ["(aucun)"]
    return L


def _transcription(etat: dict, msgs: list, nb: int) -> list[str]:
    res = []
    for m in (msgs or [])[-nb:] if nb else []:
        texte = str(m.get("texte", ""))
        if not texte.strip():
            continue
        if m.get("role") == "joueur":
            res.append(f"- Le joueur : {texte}")
        else:
            n = etat["nations"].get(m.get("nation"))
            if n:
                res.append(f"- {n['dirigeant'] or 'Le dirigeant'} ({n['nom']}) : {texte}")
    return res


def trouver_conference(etat: dict, cid: str) -> dict | None:
    return next((c for c in etat.get("conferences") or [] if c.get("id") == cid), None)


# ------------------------------------------------------------------ la requête d'une aide
def _historique(msgs: list, role_ia: str, nb: int) -> list[dict]:
    res = []
    for m in (msgs or [])[-nb:] if nb else []:
        texte = str(m.get("texte", ""))
        if texte.strip():
            res.append({"role": "user" if m.get("de") == "joueur" else "assistant", "content": texte})
    return res


def construire_aide(etat: dict, noms_terr: dict[str, str], genre: str, num_ctx: int,
                    message: str = "", nation: str = "", invites: list[str] | None = None,
                    conference: str = "") -> tuple[list[dict], dict]:
    """Les messages à envoyer pour une aide, réduits au besoin pour tenir dans `num_ctx` - 4 096 jetons.

    On réduit d'abord les événements, puis l'historique de la conversation ; jamais la consigne, la fiche
    de la nation ni le message du joueur. Lève ContexteTropPetit si cela ne suffit pas."""
    if genre not in GENRES:
        raise ValueError("aide inconnue")
    budget = num_ctx - RESERVE_REPONSE
    jetons = 0
    for nb_ev, nb_msg in ((15, MESSAGES_ENVOYES), (8, MESSAGES_ENVOYES), (8, 10), (4, 6), (2, 2), (0, 1)):
        if genre == "rapport":
            ctx = contexte_joueur(etat, noms_terr, nb_ev)
            messages = [{"role": "system", "content": CONSIGNE_RAPPORT},
                        {"role": "user", "content": "\n".join(ctx) + "\n\nRédige le rapport de situation (objet JSON)."}]
        elif genre == "conseiller":
            ctx = contexte_joueur(etat, noms_terr, nb_ev)
            messages = ([{"role": "system", "content": CONSIGNE_CONSEILLER + "\n" + "\n".join(ctx)}]
                        + _historique(etat.get("conseiller"), "conseiller", nb_msg)
                        + [{"role": "user", "content": message}])
        elif genre == "conference":
            if not invites or any(i not in etat["nations"] for i in invites):
                raise ValueError("nation inconnue")
            conf = trouver_conference(etat, conference) or {}
            ctx = contexte_conference(etat, invites, noms_terr, nb_ev)
            # Un invité arrivé en cours de route ne doit pas lire ce qui s'est dit avant lui (secrets) :
            # la transcription repart de la dernière invitation, pour tous.
            msgs = (conf.get("messages") or [])[int(conf.get("coupure") or 0):]
            hist = _transcription(etat, msgs, nb_msg)
            corps = "\n".join(ctx) + "\n\n## Conversation jusqu'ici\n" + ("\n".join(hist) or "(rien encore)")
            corps += (f"\n\n## Nouveau message du joueur\n{message}\n\nFais répondre chaque dirigeant, dans l'ordre : "
                      + ", ".join(invites) + ". (objet JSON)")
            messages = [{"role": "system", "content": consigne_conference(
                            [(i, etat["nations"][i]["nom"], etat["nations"][i]["dirigeant"]) for i in invites])},
                        {"role": "user", "content": corps}]
        else:
            if nation not in etat["nations"]:
                raise ValueError("nation inconnue")
            n = etat["nations"][nation]
            ctx = contexte_dirigeant(etat, nation, noms_terr, nb_ev)
            conv = (etat.get("diplomatie") or {}).get(nation) or []
            messages = ([{"role": "system", "content": consigne_dirigeant(n["nom"], n["dirigeant"]) + "\n" + "\n".join(ctx)}]
                        + _historique(conv, "dirigeant", nb_msg)
                        + [{"role": "user", "content": message}])
        jetons = estimer_jetons(messages)
        if jetons <= budget:
            return messages, {"jetons": jetons, "budget": budget, "evenements": nb_ev, "messages": nb_msg}
    raise ContexteTropPetit(
        f"Cette demande ne tient pas dans le contexte de {num_ctx} jetons (il en faut environ {jetons + RESERVE_REPONSE}). "
        "Augmentez la taille de contexte dans les réglages.")


# ------------------------------------------------------------------ lecture des réponses
def _propre(v, maxi: int) -> str:
    return " ".join(str(v).split())[:maxi] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def lire_conversation(texte: str) -> tuple[str | None, list[str]]:
    """Le texte de la réponse d'un conseiller ou d'un dirigeant. Un texte sans JSON est accepté tel quel
    (sans bloc <think>) ; un JSON cassé ou sans « reponse » provoque une relance."""
    obj, fautes = lire_reponse(texte)
    if obj is None:
        brut = _sans_reflexion(texte)
        if brut and "{" not in brut:
            return brut[:LONGUEUR_REPONSE], []
        return None, fautes
    rep = next((_propre(obj[k], LONGUEUR_REPONSE) for k in ("reponse", "réponse", "texte", "message") if k in obj), "")
    if not rep:
        return None, ["la clé « reponse » est absente ou vide"]
    return rep, []


def _sans_reflexion(texte: str) -> str:
    import re
    t = re.sub(r"<think>.*?</think>", "", texte or "", flags=re.S | re.I)
    t = re.sub(r"<think>.*\Z", "", t, flags=re.S | re.I)
    return t.strip()


def lire_conference(texte: str, invites: list[tuple[str, str]]) -> tuple[list[dict] | None, list[str], list[str]]:
    """Les réponses d'une conférence. `invites` : (id, nom) dans l'ordre. Renvoie (réponses dans l'ordre
    des invités, ids sans réponse, fautes). Une nation inconnue est ignorée, un doublon aussi ; une
    réponse manquante ne fait pas perdre les autres. Aucune réponse utilisable : fautes (relance)."""
    from .tour import _norm
    obj, fautes = lire_reponse(texte)
    if obj is None:
        return None, [], fautes
    brut = obj.get("reponses")
    if isinstance(brut, dict):                       # {"id": "texte"} toléré
        brut = [{"nation": k, "texte": v} for k, v in brut.items()]
    cles = {}
    for i, nom in invites:
        cles[_norm(i)] = i
        cles.setdefault(_norm(nom), i)
    trouvees: dict[str, str] = {}
    for r in brut if isinstance(brut, list) else []:
        if not isinstance(r, dict):
            continue
        qui = cles.get(_norm(r.get("nation", "")))
        t = next((_propre(r[k], LONGUEUR_REPONSE_CONF) for k in ("texte", "reponse", "réponse", "message") if k in r), "")
        if qui and t and qui not in trouvees:
            trouvees[qui] = t
    if not trouvees:
        return None, [], ["« reponses » doit contenir une entrée {nation, texte} par dirigeant invité (nation = l'id entre crochets)"]
    ordre = [i for i, _ in invites]
    return ([{"nation": i, "texte": trouvees[i]} for i in ordre if i in trouvees],
            [i for i in ordre if i not in trouvees], [])


def lire_rapport(texte: str) -> tuple[dict | None, list[str]]:
    obj, fautes = lire_reponse(texte)
    if obj is None:
        return None, fautes
    sit = obj.get("situation")
    if isinstance(sit, list):
        sit = " ".join(str(x) for x in sit)
    situation = _propre(sit, 1500)
    sugg = [" ".join(x.split())[:LONGUEUR_ORDRE] for x in _liste_textes(obj.get("suggestions"))][:SUGGESTIONS]
    f = []
    if not situation:
        f.append("« situation » doit être un paragraphe de texte non vide")
    if len(sugg) < SUGGESTIONS:
        f.append(f"« suggestions » doit contenir {SUGGESTIONS} ordres")
    if f:
        return None, f
    return {"situation": situation,
            "menaces": [x[:400] for x in _liste_textes(obj.get("menaces"))][:6],
            "occasions": [x[:400] for x in _liste_textes(obj.get("occasions"))][:6],
            "suggestions": sugg}, []


def message_relance(fautes: list[str]) -> str:
    return ("Ta réponse précédente n'est pas exploitable :\n" + "\n".join(f"- {x}" for x in fautes)
            + "\nRenvoie l'objet JSON complet, corrigé, sans aucun texte autour.")


def nettoyer_message(v) -> str:
    """Le message du joueur : texte non vide, 1 000 caractères au plus. Lève ValueError."""
    if not isinstance(v, str):
        raise ValueError("Le message doit être un texte.")
    v = "\n".join(" ".join(l.split()) for l in v.strip().splitlines())
    if not v:
        raise ValueError("Écrivez un message.")
    if len(v) > LONGUEUR_MESSAGE:
        raise ValueError(f"Un message ne peut pas dépasser {LONGUEUR_MESSAGE} caractères.")
    return v


def ajouter_messages(liste: list, etat: dict, joueur: str, reponse: str, de_ia: str) -> list:
    """Ajoute l'échange à une conversation (bornée à MESSAGES_GARDES)."""
    marque = {"tour": etat["tour"], "date": etat["date"]}
    liste = list(liste or [])
    liste += [{"de": "joueur", "texte": joueur, **marque}, {"de": de_ia, "texte": reponse, **marque}]
    return liste[-MESSAGES_GARDES:]


def ajouter_a_conference(conf: dict, etat: dict, joueur: str, reponses: list[dict]) -> None:
    """Ajoute le message du joueur puis les réponses (dans l'ordre) à une conférence, bornée à MESSAGES_GARDES."""
    tour = etat["tour"]
    msgs = list(conf.get("messages") or [])
    msgs.append({"role": "joueur", "texte": joueur, "tour": tour})
    msgs += [{"role": "dirigeant", "nation": r["nation"], "texte": r["texte"], "tour": tour} for r in reponses]
    conf["messages"] = msgs[-MESSAGES_GARDES:]
