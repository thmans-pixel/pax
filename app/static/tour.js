// Onglets, saisie des ordres, lancement du tour et suivi de sa progression.
(function () {
  var base = document.body.dataset.base || '';
  var zone = document.getElementById('zone-avancer');

  // -- onglets
  var onglets = document.querySelectorAll('.onglets button[data-onglet]');
  function montrer(nom) {
    onglets.forEach(function (b) { b.classList.toggle('actif', b.dataset.onglet === nom); });
    document.querySelectorAll('.volet').forEach(function (v) { v.hidden = v.dataset.volet !== nom; });
  }
  onglets.forEach(function (b) { b.addEventListener('click', function () { montrer(b.dataset.onglet); }); });

  if (!zone) return;
  var pid = zone.dataset.partie;
  var liste = document.getElementById('liste-ordres');
  var bouton = document.getElementById('avancer');
  var progression = document.getElementById('progression');
  var faute = document.getElementById('faute-tour');
  var duree = null;
  document.querySelectorAll('#durees .puce').forEach(function (p) {
    if (p.classList.contains('choisie')) duree = p.dataset.duree;
    p.addEventListener('click', function () {
      document.querySelectorAll('#durees .puce').forEach(function (q) { q.classList.remove('choisie'); });
      p.classList.add('choisie');
      duree = p.dataset.duree;
    });
  });

  // -- ordres : de 1 à 10
  document.getElementById('ajouter-ordre').addEventListener('click', function () {
    if (liste.children.length >= parseInt(liste.dataset.max, 10)) return;
    var li = document.createElement('li');
    var t = document.createElement('textarea');
    t.rows = 2; t.maxLength = parseInt(liste.dataset.longueur, 10); t.placeholder = 'Écrivez un ordre…';
    li.appendChild(t);
    liste.appendChild(li);
    t.focus();
  });
  function ordres() {
    return Array.prototype.map.call(liste.querySelectorAll('textarea'), function (t) { return t.value; })
      .filter(function (v) { return v.trim(); });
  }

  function bloquer(oui) {
    bouton.dataset.occupe = oui ? '1' : '';
    var badge = document.getElementById('ia-statut');
    bouton.disabled = oui || !(badge && badge.dataset.etat === 'pret');
    liste.querySelectorAll('textarea').forEach(function (t) { t.readOnly = oui; });
    var a = document.getElementById('annuler');
    if (a) a.disabled = oui;
  }
  function dire(texte, alerte) {
    faute.hidden = !alerte; faute.textContent = alerte || '';
    progression.hidden = !texte; progression.textContent = texte || '';
  }
  function suivre() {
    fetch(base + '/partie/' + pid + '/tour', { headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.etat === 'aucun') { bloquer(false); dire(''); return; }
        if (d.etat === 'termine') { location.reload(); return; }
        if (d.etat === 'echec') { bloquer(false); dire('', d.message); montrer('ordres'); return; }
        bloquer(true);
        var t = d.message;
        if (d.etat === 'ecriture') {
          t += ' ' + d.mots + ' mots reçus · ' + Math.floor(d.secondes / 60) + ' min ' + (d.secondes % 60) + ' s';
        }
        dire(t);
        setTimeout(suivre, 1000);
      })
      .catch(function () { dire('', 'Le jeu ne répond pas ; nouvel essai…'); setTimeout(suivre, 3000); });
  }

  bouton.addEventListener('click', function () {
    var o = ordres();
    if (!o.length) { dire('', 'Écrivez au moins un ordre.'); return; }
    dire('Envoi…');
    bloquer(true);
    fetch(base + '/partie/' + pid + '/tour', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ ordres: o, duree: duree })
    }).then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (x) {
        if (x[0] === 202) { suivre(); } else { bloquer(false); dire('', x[1].message); }
      })
      .catch(function () { bloquer(false); dire('', 'Le jeu ne répond pas.'); });
  });

  suivre();   // reprend l'affichage si un tour est déjà en cours (page rechargée)
})();
