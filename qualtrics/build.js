// Pizza Builder - main build (page 2)
// Paste into the JavaScript of a Text/Graphic question on its own page (question text can be empty
// or hold your instructions). The script loads pizza-builder.js from GitHub via jsDelivr.
// Embedded data it writes (declare these in the Survey Flow, see README): pz_final, pz_events, pz_summary, pz_counts

Qualtrics.SurveyEngine.addOnload(function () {
  this.hideNextButton();
});

Qualtrics.SurveyEngine.addOnReady(function () {
  var q = this;
  var SRC = 'https://cdn.jsdelivr.net/gh/berbelekhieronim/eye-tracking-library@COMMIT/pizza-builder/pizza-builder.js';
  var save = function (k, v) {
    try { Qualtrics.SurveyEngine.setEmbeddedData(k, v); } catch (e) {}
    try { Qualtrics.SurveyEngine.setJSEmbeddedData(k, v); } catch (e) {}
  };
  var box = document.createElement('div');
  box.style.marginTop = '8px';
  q.getQuestionContainer().appendChild(box);

  function start() {
    PizzaBuilder.mount(box, {
      mode: 'build',
      condition: '${e://Field/condition}',   // optional: any condition label set earlier in the Survey Flow
      // minSeconds: 20,                       // optional: earliest moment "I'm done" becomes available
      // prompt: 'Make the pizza you would like to eat. ...',
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
      save('pz_error', 'load-failed');
      box.textContent = 'This task could not load. Please continue to the next page.';
      q.showNextButton();
    };
    document.head.appendChild(s);
  }
});
