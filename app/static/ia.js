// Dit si le PC de l'IA répond, et grise les boutons qui en ont besoin.
(function () {
  var badge = document.getElementById('ia-statut');
  var base = document.body.dataset.base || '';
  function boutons(pret, message) {
    document.querySelectorAll('.btn-ia').forEach(function (b) {
      if (b.dataset.bientot) {
        b.disabled = true;
        b.title = 'Disponible à ' + b.dataset.bientot + '.';
        return;
      }
      b.disabled = !pret || b.dataset.occupe === '1';
      b.title = pret ? '' : message;
    });
  }
  function maj() {
    fetch(base + '/api/ia/statut', { headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        if (badge) {
          badge.textContent = 'IA : ' + s.message;
          badge.dataset.etat = s.pret ? 'pret' : (s.ok ? 'incomplet' : 'hors');
          badge.title = s.detail || '';
        }
        boutons(s.pret, s.message);
      })
      .catch(function () {
        if (badge) { badge.textContent = 'IA : état inconnu'; badge.dataset.etat = 'hors'; }
        boutons(false, "L'état de l'IA est inconnu.");
      });
  }
  maj();
  setInterval(maj, 30000);
})();
