// node tests/test_ticket_check.js — pure helpers of the one-ticket checker against the real archive.
const assert = require("assert");
const { TicketCheck, tierOf } = require("../assets/js/checker.js");
const max = require("../data/lotto-max.json"), l649 = require("../data/lotto-649.json");
const last = max.draws[max.draws.length - 1];
// exact draw date: the winning line itself matches 7 of 7
let r = TicketCheck.drawsBetween(max.draws, last[0], last[0]);
assert.strictEqual(r.length, 1);
let m = TicketCheck.match(last[1].slice(), r[0]);
assert.deepStrictEqual(m, { m: 7, b: false });
assert.strictEqual(tierOf("max", 7, false), 0);
// a non-draw date (a Monday) gives nothing and nearest draws either side
const iso = max.draws[max.draws.length - 2][0];
const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + 1);
const gap = d.toISOString().slice(0, 10);
if (gap !== last[0]) {
  assert.strictEqual(TicketCheck.drawsBetween(max.draws, gap, gap).length, 0);
  const n = TicketCheck.nearest(max.draws, gap);
  assert.strictEqual(n.before[0], iso); assert.ok(n.after[0] > gap);
}
// multi-draw range is inclusive and ordered
const a = max.draws[max.draws.length - 5][0];
assert.strictEqual(TicketCheck.drawsBetween(max.draws, a, last[0]).length, 5);
// 6/49: two main numbers is the Free Play tier, two + bonus its own tier, bonus counted only when on the line
const d649 = l649.draws[l649.draws.length - 1];
const two = [d649[1][0], d649[1][1]];
const fill = []; for (let x = 1; x <= 49 && fill.length < 4; x++) if (!d649[1].includes(x) && x !== d649[2]) fill.push(x);
assert.deepStrictEqual(TicketCheck.match(two.concat(fill), d649), { m: 2, b: false });
assert.strictEqual(tierOf("649", 2, false), 6);
assert.strictEqual(tierOf("649", 2, true), 5);
// archive sanity: dates strictly increasing, right count of numbers
for (const [data, k] of [[max, 7], [l649, 6]]) {
  for (let i = 1; i < data.draws.length; i++) assert.ok(data.draws[i][0] > data.draws[i - 1][0], data.draws[i][0]);
  data.draws.slice(-100).forEach((x) => assert.strictEqual(x[1].length, k));
}
console.log("ticket check tests: OK");
