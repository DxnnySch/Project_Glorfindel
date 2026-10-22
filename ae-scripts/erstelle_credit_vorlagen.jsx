// After-Effects-Skript (ExtendScript), ungetestetes Skelett: legt je Credit-Vorlage eine Komposition an.
// Ziel laut Projektheft 5.4: Credit-Vorlagen (links/einzeln und rechts) als Textkomposition, damit Premiere sie per Dynamic Link oder als MOGRT nutzt.
(function () {
  var proj = app.project || app.newProject();
  var names = ["Credit links", "Credit rechts"];
  app.beginUndoGroup("Glorfindel Credit-Vorlagen");
  for (var i = 0; i < names.length; i++) {
    var comp = proj.items.addComp(names[i], 1920, 1080, 1, 6, 23.976);
    var t = comp.layers.addText("© künstler");
    t.name = "Credit-Text";
  }
  app.endUndoGroup();
})();
