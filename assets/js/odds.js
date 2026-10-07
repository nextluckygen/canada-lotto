/* Odds calculator. Official odds per play are embedded in the page (data-odds). */
(function () {
  "use strict";
  function fmtOdds(x) { return x >= 100 ? Math.round(x).toLocaleString("en-CA") : x.toFixed(1); }
  function pct(p) { if (p > 0.999) return "over 99.9%"; return p >= 0.001 ? (p * 100).toFixed(1) + "%" : (p * 100).toFixed(4) + "%"; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function init() {
    var box = document.getElementById("calc");
    if (!box) return;
    var data = JSON.parse(box.getAttribute("data-odds"));
    function v(name) { return box.querySelector('[data-in="' + name + '"]'); }
    function o(name) { return box.querySelector('[data-out="' + name + '"]'); }
    function clamp(x, lo, hi) { x = Math.floor(Number(x) || lo); return Math.max(lo, Math.min(hi, x)); }
    function update() {
      var g = data[v("game").value];
      var plays = clamp(v("plays").value, 1, 100), dpw = clamp(v("dpw").value, 1, 2), weeks = clamp(v("weeks").value, 1, 52);
      var n = plays * dpw * weeks;
      var cost = n * g.price;
      var pj = 1 / g.tiers[0][2];
      var yj = 1 - Math.pow(1 - pj, n);
      o("n").textContent = n.toLocaleString("en-CA");
      o("cost").textContent = "$" + cost.toLocaleString("en-CA");
      o("jp").textContent = "1 in " + Math.round(1 / yj).toLocaleString("en-CA");
      o("rows").innerHTML = g.tiers.map(function (t) {
        var p = 1 / t[2], y = 1 - Math.pow(1 - p, n);
        return '<tr><td class="font-bold">' + esc(t[0]) + "</td><td>" + esc(t[1]) + '</td><td class="tnum">1 in ' + fmtOdds(t[2]) + '</td><td class="tnum">' + pct(y) + "</td></tr>";
      }).join("");
      var years = 1 / (pj * n);
      var flips = Math.round(Math.log2(g.tiers[0][2]));
      var free = g.tiers[g.tiers.length - 1];
      o("compare").innerHTML =
        "<li>🗓️ At this rate you would expect to wait about <strong>" + Math.round(years).toLocaleString("en-CA") + " years</strong> for one jackpot win on average.</li>" +
        "<li>🪙 One play hitting the jackpot is about as likely as calling <strong>" + flips + " coin flips</strong> in a row correctly.</li>" +
        "<li>💵 Over a year you spend <strong>$" + cost.toLocaleString("en-CA") + "</strong>; any prize at all comes about once every " + g.any + " plays, and the most common one is " + esc(free[0]) + " (" + esc(free[1]) + ").</li>";
    }
    box.addEventListener("input", update);
    box.addEventListener("change", update);
    update();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
