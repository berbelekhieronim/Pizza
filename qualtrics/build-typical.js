// Pizza Builder - optional second build: "a typical participant" (perceived norm)
// Paste into the JavaScript of a Text/Graphic question on its own page (question text can be empty
// or hold your instructions). The script loads pizza-builder.js from GitHub via jsDelivr.
// Embedded data it writes (declare these in the Survey Flow, see README): pzt_final, pzt_events, pzt_summary, pzt_counts

Qualtrics.SurveyEngine.addOnload(function () {
  this.hideNextButton();
});

Qualtrics.SurveyEngine.addOnReady(function () {
  var q = this;
  var SRC = 'https://cdn.jsdelivr.net/gh/berbelekhieronim/pizza@f52049b11f357ce9ac0cfa7a7ff9342bd487a869/pizza-builder.js';
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
      prefix: 'pzt_',
      condition: '${e://Field/condition}',
      prompt: 'Now make the pizza you think a typical participant in this study would choose. Drag toppings onto the pizza; drag a topping off to remove it.',
      // nutrition: true,                      // optional: live nutrition panel under the pizza (see README, Nutrition panel)
      onSave: save,
      onFinish: function () { q.showNextButton(); q.clickNextButton(); }   // the task's own button moves on
    });
  }
  if (window.PizzaBuilder) start();
  else {
    var s = document.createElement('script');
    s.src = SRC;
    s.onload = start;
    s.onerror = function () {       // never trap a participant: record the failure and let them continue
      save('pzt_error', 'load-failed');
      box.textContent = 'This task could not load. Please continue to the next page.';
      q.showNextButton();
    };
    document.head.appendChild(s);
  }
});
