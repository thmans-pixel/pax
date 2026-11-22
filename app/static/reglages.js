// Page Réglages : tester Ollama et remplir la liste des modèles installés.
(function () {
  var base = document.body.dataset.base || '';
  var bouton = document.getElementById('tester');
  var champ = document.getElementById('ollama_adresse');
  var sortie = document.getElementById('resultat-test');
  var select = document.getElementById('modele');
  if (!bouton) return;

  function remplir(modeles) {
    var actuel = select.dataset.actuel || select.value;
    select.innerHTML = '';
    var vide = document.createElement('option');
    vide.value = ''; vide.textContent = '— choisir un modèle —';
    select.appendChild(vide);
    var trouve = false;
    modeles.forEach(function (m) {
      var o = document.createElement('option');
      o.value = m; o.textContent = m;
      if (m === actuel) { o.selected = true; trouve = true; }
      select.appendChild(o);
    });
    if (actuel && !trouve) {
      var o = document.createElement('option');
      o.value = actuel; o.textContent = actuel + ' (non installé)'; o.selected = true;
      select.appendChild(o);
    }
  }

  function tester() {
    sortie.textContent = 'Test en cours…';
    sortie.className = 'discret';
    fetch(base + '/api/ia/tester', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adresse: champ.value })
    }).then(function (r) { return r.json(); }).then(function (res) {
      sortie.textContent = res.ok
        ? 'Connexion OK — ' + res.modeles.length + ' modèle(s) installé(s).'
        : res.message;
      sortie.className = res.ok ? 'ok' : 'alerte';
      if (res.ok) remplir(res.modeles);
    }).catch(function () {
      sortie.textContent = 'Le test a échoué.'; sortie.className = 'alerte';
    });
  }
  bouton.addEventListener('click', tester);
  tester();
})();
