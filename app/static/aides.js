// Les aides de l'IA : rapport de situation, conseiller, dirigeants. Tout texte venu de l'IA
// ou du joueur est inséré par textContent, jamais comme du HTML.
(function () {
  var base = document.body.dataset.base || '';
  var zone = document.getElementById('zone-avancer');
  var brut = document.getElementById('pax-aides');
  if (!brut) return;
  var donnees = JSON.parse(brut.textContent);
  var pid = (zone && zone.dataset.partie) || location.pathname.split('/').filter(Boolean).pop();
  var occupe = false;

  function el(nom, classe, texte) {
    var e = document.createElement(nom);
    if (classe) e.className = classe;
    if (texte !== undefined) e.textContent = texte;
    return e;
  }

  // -- conversations
  function bulle(conteneur, de, texte, nom) {
    var m = el('div', 'msg ' + (de === 'joueur' ? 'joueur' : 'ia'));
    m.appendChild(el('span', 'qui', de === 'joueur' ? 'Vous' : nom));
    m.appendChild(document.createTextNode(texte));
    conteneur.appendChild(m);
    conteneur.scrollTop = conteneur.scrollHeight;
  }
  function afficherConversation(conteneur, msgs, nom) {
    conteneur.textContent = '';
    (msgs || []).forEach(function (m) { bulle(conteneur, m.de, m.texte, nom); });
  }
  var convConseiller = document.getElementById('conv-conseiller');
  var convDiplo = document.getElementById('conv-diplomatie');
  var selectNation = document.getElementById('diplo-nation');
  function nomNation() {
    var o = selectNation.options[selectNation.selectedIndex];
    return o && o.value ? o.textContent.split(' — ')[0] : 'Dirigeant';
  }
  afficherConversation(convConseiller, donnees.conseiller, 'Conseiller');

  // -- conférences : plusieurs dirigeants autour d'une même table
  donnees.conferences = donnees.conferences || [];
  var vivantes = donnees.vivantes || [];
  var max = donnees.max_conference || 5;
  var cases = document.getElementById('conf-cases');
  var fieldsetNouvelle = document.getElementById('conf-nouvelle');
  var blocInviter = document.getElementById('conf-inviter');
  var selectInviter = document.getElementById('conf-inviter-nation');
  function nomDe(id) { return (donnees.noms || {})[id] || id; }
  function titreConference(c) {
    return 'Conférence : ' + c.nations.map(nomDe).join(', ');
  }
  function conferenceChoisie() {
    var v = selectNation.value;
    if (v.indexOf('conf:') !== 0 || v === 'conf:nouvelle') return null;
    return donnees.conferences.filter(function (c) { return c.id === v.slice(5); })[0] || null;
  }
  function fauteConf(texte) {
    var f = document.getElementById('conf-faute');
    if (f) { f.hidden = !texte; f.textContent = texte || ''; }
  }
  function remplirOptionsConferences(garder) {
    Array.prototype.slice.call(selectNation.options).forEach(function (o) {
      if (o.dataset.conf) selectNation.removeChild(o);
    });
    var apres = selectNation.querySelector('option[value="conf:nouvelle"]');
    var ref = apres ? apres.nextSibling : selectNation.options[1];
    donnees.conferences.forEach(function (c) {
      var o = el('option', '', titreConference(c));
      o.value = 'conf:' + c.id;
      o.dataset.conf = '1';
      selectNation.insertBefore(o, ref);
    });
    if (garder) selectNation.value = garder;
  }
  function remplirCases() {
    cases.textContent = '';
    vivantes.forEach(function (id) {
      var l = el('label');
      var c = document.createElement('input');
      c.type = 'checkbox'; c.value = id;
      c.addEventListener('change', function () {
        var n = cases.querySelectorAll('input:checked').length;
        if (n > max) { c.checked = false; fauteConf('Une conférence réunit ' + max + ' nations au plus.'); } else fauteConf('');
      });
      l.appendChild(c);
      l.appendChild(document.createTextNode(' ' + nomDe(id)));
      cases.appendChild(l);
    });
  }
  function remplirInviter(c) {
    selectInviter.textContent = '';
    var restantes = vivantes.filter(function (id) { return c.nations.indexOf(id) < 0; });
    restantes.forEach(function (id) {
      var o = el('option', '', nomDe(id)); o.value = id; selectInviter.appendChild(o);
    });
    blocInviter.hidden = !(restantes.length && c.nations.length < max);
  }
  function afficherConference(c) {
    convDiplo.textContent = '';
    c.messages.forEach(function (m) {
      var qui = nomDe(m.nation) + ((donnees.dirigeants || {})[m.nation] ? ' — ' + donnees.dirigeants[m.nation] : '');
      bulle(convDiplo, m.role === 'joueur' ? 'joueur' : 'ia', m.texte, qui);
    });
  }
  function actualiserDiplomatie() {
    var v = selectNation.value, c = conferenceChoisie();
    fauteConf('');
    fieldsetNouvelle.hidden = v !== 'conf:nouvelle';
    blocInviter.hidden = true;
    if (v === 'conf:nouvelle') { convDiplo.textContent = ''; return; }
    if (c) { afficherConference(c); remplirInviter(c); return; }
    afficherConversation(convDiplo, (donnees.diplomatie || {})[v], nomNation());
  }
  remplirOptionsConferences();
  remplirCases();
  selectNation.addEventListener('change', actualiserDiplomatie);
  var bInviter = document.getElementById('conf-inviter-bouton');
  bInviter.addEventListener('click', function () {
    var c = conferenceChoisie();
    if (!c || !selectInviter.value) return;
    fetch(base + '/partie/' + pid + '/conference/' + c.id + '/inviter', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ nation: selectInviter.value })
    }).then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (x) {
        if (x[0] === 200) {
          c.nations = x[1].nations;
          remplirOptionsConferences('conf:' + c.id);
          actualiserDiplomatie();
        } else fauteConf(x[1].message || 'Invitation refusée.');
      })
      .catch(function () { fauteConf('Le jeu ne répond pas.'); });
  });
  // utilisé par la roue : ouvre Diplomatie sur une nation, ou invite à la conférence affichée
  window.paxDiplomatie = {
    ouvrir: function (nid) {
      selectNation.value = nid;
      actualiserDiplomatie();
    },
    conferenceAffichee: function () { return conferenceChoisie(); },
    inviter: function (nid) {
      selectInviter.value = nid;
      bInviter.click();
    }
  };

  // -- rapport
  function ajouterOrdre(texte, faute) {
    var liste = document.getElementById('liste-ordres');
    if (!liste) return;
    var champs = liste.querySelectorAll('textarea');
    var vide = Array.prototype.filter.call(champs, function (t) { return !t.value.trim(); })[0];
    if (!vide) {
      if (champs.length >= parseInt(liste.dataset.max, 10)) { faute.hidden = false; faute.textContent = 'Déjà ' + liste.dataset.max + ' ordres : retirez-en un d’abord.'; return; }
      document.getElementById('ajouter-ordre').click();
      vide = liste.querySelectorAll('textarea');
      vide = vide[vide.length - 1];
    }
    vide.value = texte;
    faute.hidden = true;
  }
  function liste(titre, items) {
    var f = document.createDocumentFragment();
    if (!items || !items.length) return f;
    f.appendChild(el('h4', '', titre));
    var ul = el('ul');
    items.forEach(function (x) { ul.appendChild(el('li', '', x)); });
    f.appendChild(ul);
    return f;
  }
  var zoneRapport = document.getElementById('rapport');
  var fauteRapport = document.getElementById('rapport-faute');
  function afficherRapport(r) {
    if (!r || !zoneRapport) return;
    zoneRapport.textContent = '';
    zoneRapport.hidden = false;
    zoneRapport.appendChild(el('p', 'discret', 'Rapport établi au tour ' + r.tour + ' (' + r.date + ')'));
    zoneRapport.appendChild(el('p', '', r.situation));
    zoneRapport.appendChild(liste('Menaces', r.menaces));
    zoneRapport.appendChild(liste('Occasions', r.occasions));
    if (r.suggestions && r.suggestions.length) {
      zoneRapport.appendChild(el('h4', '', 'Ordres suggérés'));
      r.suggestions.forEach(function (s) {
        var ligne = el('div', 'suggestion');
        var b = el('button', 'btn', '+ ajouter');
        b.type = 'button';
        b.title = 'Ajouter cet ordre à vos ordres';
        b.addEventListener('click', function () { ajouterOrdre(s, fauteRapport); });
        ligne.appendChild(b);
        ligne.appendChild(el('span', '', s));
        zoneRapport.appendChild(ligne);
      });
    }
  }
  afficherRapport(donnees.rapport);

  // -- envoi d'une demande et suivi (même principe que le tour : la page interroge chaque seconde)
  function bloquer(oui) {
    occupe = oui;
    document.querySelectorAll('#rapport-bouton, #conseiller-envoyer, #diplomatie-envoyer').forEach(function (b) {
      b.dataset.occupe = oui ? '1' : '';
      var badge = document.getElementById('ia-statut');
      b.disabled = oui || !(badge && badge.dataset.etat === 'pret');
    });
  }
  function dire(genre, texte, alerte) {
    if (genre === 'conference') genre = 'diplomatie';
    var s = document.getElementById(genre + '-statut'), f = document.getElementById(genre + '-faute');
    if (s) { s.hidden = !texte; s.textContent = texte || ''; }
    if (f) { f.hidden = !alerte; f.textContent = alerte || ''; }
  }
  function terminer(d, genre) {
    var r = d.resultat || {};
    if (d.genre === 'rapport') { afficherRapport(r.rapport); donnees.rapport = r.rapport; return; }
    var msg = envoye[d.genre];
    if (d.genre === 'conseiller') {
      donnees.conseiller = (donnees.conseiller || []).concat([{ de: 'joueur', texte: msg }, { de: 'conseiller', texte: r.reponse }]);
      afficherConversation(convConseiller, donnees.conseiller, 'Conseiller');
      document.getElementById('conseiller-texte').value = '';
    } else if (d.genre === 'conference') {
      var c = donnees.conferences.filter(function (x) { return x.id === r.conference; })[0];
      if (!c) { c = { id: r.conference, nations: r.nations, messages: [] }; donnees.conferences.push(c); }
      c.messages.push({ role: 'joueur', texte: msg });
      r.reponses.forEach(function (x) { c.messages.push({ role: 'dirigeant', nation: x.nation, texte: x.texte }); });
      remplirOptionsConferences('conf:' + c.id);
      actualiserDiplomatie();
      document.getElementById('diplomatie-texte').value = '';
      if (r.manquants && r.manquants.length) {
        dire('diplomatie', '', r.manquants.map(nomDe).join(', ') + (r.manquants.length > 1 ? ' n’ont pas répondu.' : ' n’a pas répondu.'));
      }
    } else {
      var l = (donnees.diplomatie[r.nation] = (donnees.diplomatie[r.nation] || []).concat([{ de: 'joueur', texte: msg }, { de: 'dirigeant', texte: r.reponse }]));
      if (selectNation.value === r.nation) afficherConversation(convDiplo, l, nomNation());
      document.getElementById('diplomatie-texte').value = '';
    }
  }
  var envoye = {};
  var premiere = true;
  function suivre(genre) {
    var q = premiere ? '?initial=1' : '';
    premiere = false;
    fetch(base + '/partie/' + pid + '/aide' + q, { headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var g = d.genre || genre;
        if (d.etat === 'aucun') { bloquer(false); return; }
        if (d.etat === 'termine') {
          bloquer(false); dire(g, '');
          if (envoye[d.genre] === undefined && d.genre !== 'rapport') { location.reload(); return; }
          terminer(d); return;
        }
        if (d.etat === 'echec') { bloquer(false); dire(g, '', d.message); return; }
        bloquer(true); dire(g, d.message);
        setTimeout(function () { suivre(g); }, 1000);
      })
      .catch(function () { dire(genre, '', 'Le jeu ne répond pas ; nouvel essai…'); setTimeout(function () { suivre(genre); }, 3000); });
  }
  function demander(genre, corps) {
    if (occupe) return;
    dire(genre, 'Envoi…');
    bloquer(true);
    corps.genre = genre;
    envoye[genre] = corps.message;
    fetch(base + '/partie/' + pid + '/aide', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(corps)
    }).then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (x) {
        if (x[0] === 202) { premiere = false; suivre(genre); } else { bloquer(false); dire(genre, '', x[1].message); }
      })
      .catch(function () { bloquer(false); dire(genre, '', 'Le jeu ne répond pas.'); });
  }

  var bRapport = document.getElementById('rapport-bouton');
  if (bRapport) bRapport.addEventListener('click', function () { demander('rapport', {}); });
  var bC = document.getElementById('conseiller-envoyer');
  if (bC) bC.addEventListener('click', function () {
    var t = document.getElementById('conseiller-texte').value.trim();
    if (!t) { dire('conseiller', '', 'Écrivez un message.'); return; }
    demander('conseiller', { message: t });
  });
  var bD = document.getElementById('diplomatie-envoyer');
  if (bD) bD.addEventListener('click', function () {
    var t = document.getElementById('diplomatie-texte').value.trim();
    var v = selectNation.value;
    if (!v) { dire('diplomatie', '', 'Choisissez une nation.'); return; }
    if (!t) { dire('diplomatie', '', 'Écrivez un message.'); return; }
    if (v === 'conf:nouvelle') {
      var ids = Array.prototype.map.call(cases.querySelectorAll('input:checked'), function (c) { return c.value; });
      if (ids.length < 2) { dire('diplomatie', '', 'Cochez au moins 2 nations pour une conférence.'); return; }
      demander('conference', { message: t, nations: ids });
    } else if (v.indexOf('conf:') === 0) {
      demander('conference', { message: t, conference: v.slice(5) });
    } else {
      demander('diplomatie', { message: t, nation: v });
    }
  });

  suivre('rapport');   // reprend l'affichage si une demande est déjà en cours (page rechargée)
})();
