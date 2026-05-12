var TalariaFixture = {};
TalariaFixture.message = "talaria fixture";
TalariaFixture.first = "alpha";
TalariaFixture.second = "alpha";
TalariaFixture.when = "now";
TalariaFixture.answer = 42;
function add(left, right) {
  return left + right;
}
function alphaValue() {
  return "alpha";
}
TalariaFixture.total = add(19, 23);
TalariaFixture.third = alphaValue();
TalariaFixture.items = ["alpha", "beta", "gamma"];
for (var index = 0; index < TalariaFixture.items.length; index++) {
  TalariaFixture.items[index] = TalariaFixture.items[index] + ":" + index;
}
