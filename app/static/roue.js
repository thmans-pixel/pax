// La roue d'actions sur la carte : Parler, Ordre, Conseil, Fiche. Aucune dépendance.
// Tout texte (nom de nation ou de territoire, venu du scénario ou de l'IA) passe par textContent.
(function () {
  var svg = document.getElementById('carte');
  var brut = document.getElementById('pax-data');
  var zone = svg && svg.parentNode;
  if (!svg || !brut || !zone) return;
  var data = JSON.parse(brut.textContent);
  var DELAI_LONG = 500;      // appui long (tactile), en millisecondes
  var SEUIL = 8;             // pixels : au-delà, c'est un glisser et non un appui

  var roue = document.createElement('div');
  roue.className = 'roue';
  roue.setAttribute('role', 'menu');
  roue.hidden = true;
  var centre = document.createElement('div');
  centre.className = 'roue-centre';
  roue.appendChild(centre);
  var boutons = {};
  [['parler', 'Parler'], ['ordre', 'Ordre'], ['conseil', 'Conseil'], ['fiche', 'Fiche']].forEach(function (a) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'roue-action roue-' + a[0];
    b.setAttribute('role', 'menuitem');
    b.textContent = a[1];
    boutons[a[0]] = b;
    roue.appendChild(b);
  });
  zone.appendChild(roue);

  var courant = null;        // { nid, territoire }
  var precedent = null;      // l'élément qui avait le focus avant l'ouverture
  var ignorerClic = 0;       // horodatage jusqu'auquel un clic est ignoré (relâchement après un appui long)

  function nomNation(nid) { return (data.nations || {})[nid] || nid; }
  function fermer() {
    if (roue.hidden) return;
    roue.hidden = true;
    courant = null;
    if (precedent && precedent.focus) precedent.focus();
    precedent = null;
  }
  function onglet(nom) {
    var b = document.querySelector('.onglets button[data-onglet="' + nom + '"]');
    if (b) b.click();
  }
  function message(texte) {
    var info = document.getElementById('info-carte');
    if (info) info.textContent = texte;
  }

  // -- les quatre actions
  function parler(nid) {
    onglet('diplomatie');
    var d = window.paxDiplomatie;
    if (!d) return;
    var conf = d.conferenceAffichee();
    if (conf && conf.nations.indexOf(nid) < 0 && conf.nations.length < 5
        && window.confirm('Inviter ' + nomNation(nid) + ' à la conférence affichée ?\n(Annuler : parler à ' + nomNation(nid) + ' en tête à tête.)')) {
      d.inviter(nid);
      return;
    }
    d.ouvrir(nid);
  }
  function ordre(nid) {
    var liste = document.getElementById('liste-ordres');
    if (!liste) { message('Les ordres ne sont plus possibles : la partie est terminée.'); return; }
    var texte = (nid === data.joueur ? 'Pour ' : 'Envers ') + nomNation(nid) + ' : ';
    var champs = liste.querySelectorAll('textarea');
    var vide = Array.prototype.filter.call(champs, function (t) { return !t.value.trim(); })[0];
    if (!vide) {
      if (champs.length >= parseInt(liste.dataset.max, 10)) {
        onglet('ordres');
        message('Déjà ' + liste.dataset.max + ' ordres : retirez-en un d’abord.');
        return;
      }
      document.getElementById('ajouter-ordre').click();
      champs = liste.querySelectorAll('textarea');
      vide = champs[champs.length - 1];
    }
    vide.value = texte;
    onglet('ordres');
    vide.focus();
    vide.setSelectionRange(texte.length, texte.length);
    vide.dispatchEvent(new Event('input', { bubbles: true }));
  }
  function conseil(nid) {
    onglet('conseiller');
    var t = document.getElementById('conseiller-texte');
    if (!t) return;                      // partie terminée : pas de saisie
    t.value = 'Que penses-tu de ' + nomNation(nid) + ' ?';
    t.focus();                           // prêt à envoyer, rien n'est envoyé
  }
  function fiche(nid) {
    if (window.paxCarte) window.paxCarte.choisir(nid || null);
    var f = document.getElementById('fiche');
    if (f) { f.tabIndex = -1; f.scrollIntoView({ block: 'nearest' }); f.focus(); }
  }

  function actions(c) {
    var f = c.nid ? (data.fiches || {})[c.nid] : null;
    var vivante = !!(f && !f.disparue);
    var oui = { fiche: true };
    if (vivante) { oui.ordre = true; oui.conseil = true; oui.parler = c.nid !== data.joueur; }
    return oui;
  }
  function ouvrir(c, x, y) {
    precedent = document.activeElement;
    courant = c;
    var f = c.nid ? (data.fiches || {})[c.nid] : null;
    centre.textContent = f ? f.nom : (window.paxCarte ? window.paxCarte.nomTerritoire(c.territoire) : (c.territoire || ''));
    var oui = actions(c);
    Object.keys(boutons).forEach(function (k) { boutons[k].hidden = !oui[k]; });
    var r = zone.getBoundingClientRect();
    var marge = 90;
    var px = Math.min(Math.max(x - r.left, marge), Math.max(r.width - marge, marge));
    var py = Math.min(Math.max(y - r.top, marge), Math.max(r.height - marge, marge));
    roue.style.left = px + 'px';
    roue.style.top = py + 'px';
    roue.hidden = false;
    var premier = ['parler', 'ordre', 'conseil', 'fiche'].filter(function (k) { return oui[k]; })[0];
    boutons[premier].focus();
  }

  Object.keys(boutons).forEach(function (k) {
    boutons[k].addEventListener('click', function () {
      var c = courant;
      precedent = null;                    // l'action place elle-même le focus
      fermer();
      if (!c) return;
      ({ parler: parler, ordre: ordre, conseil: conseil, fiche: fiche })[k](c.nid);
    });
  });

  // -- ouverture au clic (carte.js ne l'envoie que pour un vrai clic, pas pour un glisser)
  svg.addEventListener('pax:pays', function (e) {
    if (Date.now() < ignorerClic) return;
    ouvrir({ nid: e.detail.nid, territoire: e.detail.territoire }, e.detail.x, e.detail.y);
  });

  // -- appui long sur écran tactile
  var appui = null;
  function annulerAppui() { if (appui) { clearTimeout(appui.minuteur); appui = null; } }
  svg.addEventListener('pointerdown', function (e) {
    annulerAppui();
    if (e.pointerType === 'mouse') return;
    var p = e.target.closest && e.target.closest('.pays');
    if (!p) return;
    appui = { x: e.clientX, y: e.clientY, nid: p.dataset.n || null, territoire: p.dataset.t };
    appui.minuteur = setTimeout(function () {
      var a = appui;
      appui = null;
      if (!a) return;
      ignorerClic = Date.now() + 1500;      // le relâchement qui suit ne doit pas rouvrir ni refermer la roue
      if (window.paxCarte) window.paxCarte.choisir(a.nid);
      ouvrir({ nid: a.nid, territoire: a.territoire }, a.x, a.y);
    }, DELAI_LONG);
  });
  window.addEventListener('pointermove', function (e) {
    if (appui && Math.abs(e.clientX - appui.x) + Math.abs(e.clientY - appui.y) > SEUIL) annulerAppui();
  });
  window.addEventListener('pointerup', annulerAppui);
  window.addEventListener('pointercancel', annulerAppui);
  svg.addEventListener('contextmenu', function (e) { if (appui || Date.now() < ignorerClic) e.preventDefault(); });

  // -- fermeture : Échap, clic ailleurs, déplacement ou zoom de la carte
  document.addEventListener('keydown', function (e) {
    if (roue.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); fermer(); return; }
    if (e.key === 'Tab') {                  // Tab tourne dans la roue
      var vis = Object.keys(boutons).map(function (k) { return boutons[k]; }).filter(function (b) { return !b.hidden; });
      var i = vis.indexOf(document.activeElement);
      e.preventDefault();
      vis[(i + (e.shiftKey ? -1 : 1) + vis.length) % vis.length].focus();
    }
  });
  document.addEventListener('pointerdown', function (e) {
    if (roue.hidden || roue.contains(e.target)) return;
    if (Date.now() < ignorerClic) return;
    fermer();
  });
  svg.addEventListener('wheel', fermer, { passive: true });
})();
