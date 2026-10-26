// Pizza Builder - follow-up ratings (page after the build)
// Paste into the JavaScript of a Text/Graphic question on its own page (question text can be empty
// or hold your instructions). The script loads pizza-builder.js from GitHub via jsDelivr.
// Embedded data it writes (declare these in the Survey Flow, see README): pzf_data

Qualtrics.SurveyEngine.addOnload(function () {
  this.hideNextButton();
});

Qualtrics.SurveyEngine.addOnReady(function () {
  var q = this;
  var SRC = 'https://cdn.jsdelivr.net/gh/berbelekhieronim/eye-tracking-library@52a9f1324242f95d4a7f249b0f12afc04d3904aa/pizza-builder/pizza-builder.js';
  var save = function (k, v) {
    try { Qualtrics.SurveyEngine.setEmbeddedData(k, v); } catch (e) {}
    try { Qualtrics.SurveyEngine.setJSEmbeddedData(k, v); } catch (e) {}
  };
  var box = document.createElement('div');
  box.style.marginTop = '8px';
  q.getQuestionContainer().appendChild(box);

  function start() {
    PizzaBuilder.mount(box, {
      mode: 'followup',
      counts: '${e://Field/pz_counts},${e://Field/__js_pz_counts}',   // which toppings were left off -> asks why
      onSave: save,
      onFinish: function () { q.showNextButton(); }
    });
  }
  if (window.PizzaBuilder) start();
  else {
    var s = document.createElement('script');
    s.src = SRC;
    s.onload = start;
    s.onerror = function () {       // never trap a participant: record the failure and let them continue
      save('pzf_error', 'load-failed');
      box.textContent = 'This task could not load. Please continue to the next page.';
      q.showNextButton();
    };
    document.head.appendChild(s);
  }
});
