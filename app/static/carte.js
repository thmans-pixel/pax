// La carte : zoom, déplacement, survol, choix d'une nation, fiche.
(function () {
  var svg = document.getElementById('carte');
  var brut = document.getElementById('pax-data');
  if (!svg || !brut) return;
  var data = JSON.parse(brut.textContent);
  var info = document.getElementById('info-carte');
  var fiche = document.getElementById('fiche');
  var choix = document.getElementById('champ-nation');
  var commencer = document.getElementById('commencer');

  // ---- zoom et déplacement ------------------------------------------------
  var vb = svg.viewBox.baseVal;
  var init = { x: vb.x, y: vb.y, w: vb.width, h: vb.height };
  var vue = { x: init.x, y: init.y, w: init.w, h: init.h };
  function appliquer() {
    vue.w = Math.min(Math.max(vue.w, init.w / 14), init.w);
    vue.h = vue.w * init.h / init.w;
    vue.x = Math.min(Math.max(vue.x, init.x), init.x + init.w - vue.w);
    vue.y = Math.min(Math.max(vue.y, init.y), init.y + init.h - vue.h);
    svg.setAttribute('viewBox', [vue.x, vue.y, vue.w, vue.h].join(' '));
  }
  function pointSvg(cx, cy) {
    var p = svg.createSVGPoint(); p.x = cx; p.y = cy;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }
  function zoomer(facteur, cx, cy) {
    var c = (cx === undefined) ? { x: vue.x + vue.w / 2, y: vue.y + vue.h / 2 } : pointSvg(cx, cy);
    vue.x = c.x - (c.x - vue.x) * facteur;
    vue.y = c.y - (c.y - vue.y) * facteur;
    vue.w *= facteur;
    appliquer();
  }
  svg.addEventListener('wheel', function (e) {
    e.preventDefault();
    zoomer(e.deltaY < 0 ? 0.8 : 1.25, e.clientX, e.clientY);
  }, { passive: false });
  var plus = document.getElementById('zoom-plus');
  var moins = document.getElementById('zoom-moins');
  var tout = document.getElementById('zoom-tout');
  if (plus) plus.addEventListener('click', function () { zoomer(0.7); });
  if (moins) moins.addEventListener('click', function () { zoomer(1 / 0.7); });
  if (tout) tout.addEventListener('click', function () { vue = { x: init.x, y: init.y, w: init.w, h: init.h }; appliquer(); });

  var glisse = null, bouge = false;
  svg.addEventListener('pointerdown', function (e) {
    glisse = { cx: e.clientX, cy: e.clientY, x: vue.x, y: vue.y };
    bouge = false;
  });
  window.addEventListener('pointermove', function (e) {
    if (!glisse) return;
    var dx = e.clientX - glisse.cx, dy = e.clientY - glisse.cy;
    if (Math.abs(dx) + Math.abs(dy) > 4) bouge = true;
    if (!bouge) return;
    var echelle = svg.getScreenCTM().a;
    vue.x = glisse.x - dx / echelle;
    vue.y = glisse.y - dy / echelle;
    appliquer();
  });
  window.addEventListener('pointerup', function () { glisse = null; });

  // ---- survol et choix ----------------------------------------------------
  function nomNation(nid) { return nid ? (data.nations[nid] || nid) : 'sans nation'; }
  svg.addEventListener('mouseover', function (e) {
    var p = e.target.closest('.pays');
    if (!p || !info) return;
    var t = p.dataset.t, n = p.dataset.n;
    var nomT = data.noms[t] || t, nomN = nomNation(n);
    info.textContent = nomT === nomN ? nomT : nomT + ' — ' + nomN;
  });

  function ligne(parent, etiquette, texte) {
    var p = document.createElement('p');
    var b = document.createElement('strong'); b.textContent = etiquette + ' ';
    p.appendChild(b); p.appendChild(document.createTextNode(texte));
    parent.appendChild(p);
  }
  function montrerFiche(nid) {
    if (!fiche) return;
    var f = data.fiches[nid];
    fiche.textContent = '';
    if (!f) { var v = document.createElement('p'); v.className = 'discret'; v.textContent = 'Aucune nation ici.'; fiche.appendChild(v); return; }
    var h = document.createElement('h2');
    var pastille = document.createElement('span'); pastille.className = 'pastille'; pastille.style.background = f.couleur;
    h.appendChild(pastille); h.appendChild(document.createTextNode(' ' + f.nom));
    fiche.appendChild(h);
    if (f.disparue) { ligne(fiche, 'Nation disparue', '— elle ne possède plus aucun territoire.'); return; }
    if (f.dirigeant) ligne(fiche, 'Dirigeant', f.dirigeant);
    if (f.regime) ligne(fiche, 'Régime', f.regime);
    var c = f.chiffres;
    ligne(fiche, 'Chiffres', 'économie ' + c.economie + ' · armée ' + c.armee + ' · stabilité ' + c.stabilite + ' · influence ' + c.influence);
    var t = f.territoires;
    ligne(fiche, 'Territoires', t.slice(0, 14).join(', ') + (t.length > 14 ? ' … (+' + (t.length - 14) + ')' : ''));
    if (f.majeure) ligne(fiche, '', 'Grande puissance du scénario.');
    if (f.joueur) ligne(fiche, '', 'C’est votre nation.');
    if (f.relation) ligne(fiche, 'Relation avec vous', (f.relation.note > 0 ? '+' : '') + f.relation.note + ' (' + f.relation.palier + ')');
    if (f.guerres) {
      if (!f.guerres.length) ligne(fiche, 'Guerres', 'aucune.');
      f.guerres.forEach(function (g) {
        ligne(fiche, 'Guerre', g.nom + ' : ' + g.camp_a.join(', ') + ' contre ' + g.camp_b.join(', ') + (g.depuis ? ' (depuis le ' + g.depuis + ')' : ''));
      });
    }
  }

  var courante = null;
  function choisir(nid) {
    courante = nid;
    svg.querySelectorAll('.pays.choisie').forEach(function (p) { p.classList.remove('choisie'); });
    if (nid) svg.querySelectorAll('.pays[data-n="' + nid + '"]').forEach(function (p) { p.classList.add('choisie'); });
    montrerFiche(nid);
    if (choix && commencer) {
      var ok = nid && data.jouables && data.jouables.indexOf(nid) >= 0;
      choix.value = ok ? nid : '';
      commencer.disabled = !ok;
    }
  }
  svg.addEventListener('click', function (e) {
    if (bouge) return;
    var p = e.target.closest('.pays');
    if (!p) return;
    choisir(p.dataset.n || null);
    // un vrai clic (pas un glisser) : la roue d'actions (roue.js) s'ouvre sur ce pays
    svg.dispatchEvent(new CustomEvent('pax:pays', {
      bubbles: true, detail: { nid: p.dataset.n || null, territoire: p.dataset.t, x: e.clientX, y: e.clientY }
    }));
  });
  window.paxCarte = { choisir: choisir, fiche: fiche, nomTerritoire: function (t) { return data.noms[t] || t; } };
  document.querySelectorAll('.puce').forEach(function (b) {
    b.addEventListener('click', function () { choisir(b.dataset.nid); });
  });
  if (data.joueur) choisir(data.joueur);
})();
