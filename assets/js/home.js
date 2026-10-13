/* Home page: "your numbers vs the latest draw". The generator lives in generator.js. */
(function () {
  "use strict";
  var LH = window.LH;

  function myLine() {
    var box = document.getElementById("my-line");
    if (!box) return;
    var lines = LH.getLines();
    var out = [];
    [["max", "Lotto Max"], ["649", "Lotto 6/49"]].forEach(function (g) {
      var line = lines[g[0]];
      var raw = box.getAttribute("data-" + g[0]);
      if (!line || !line.length || !raw) return;
      var parts = raw.split("|");
      var nums = parts[1].split("-").map(Number);
      var bonus = Number(parts[2]) || 0;
      var hits = 0, bonusHit = false;
      var balls = line.map(function (n) {
        var hit = nums.indexOf(n) >= 0;
        if (hit) hits++;
        if (n === bonus) bonusHit = true;
        return LH.ballHTML(n, "sm", hit ? "hit" : (n === bonus ? "hit" : "miss"), undefined, g[0]);
      }).join("");
      var d = new Date(parts[0] + "T12:00:00");
      var when = d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" });
      out.push('<div class="flex flex-wrap items-center gap-3 py-1"><span class="badge ' + (g[0] === "max" ? "badge-max" : "badge-649") + '">' + g[1] +
        '</span><span class="balls balls-sm">' + balls + '</span><span class="font-bold text-white">' + hits + " of " + line.length +
        (bonusHit ? " + bonus" : "") + '</span><span class="text-xs text-indigo-200">vs ' + when + ' draw · <a href="/check-my-numbers.html?game=' + g[0] +
        "&amp;n=" + line.join("-") + '">all-time check →</a></span></div>');
    });
    if (out.length) box.querySelector("[data-myline]").innerHTML = out.join("");
  }

  function init() { myLine(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
