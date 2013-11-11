module( "scripts.js" );

test("hatta._parse_date", function (assert) {
    var expected = new Date("Sat Nov 09 2013 13:10:04 GMT+0000 (UTC)");
    assert.equal(
        hatta._parse_date("2013-11-09T13:10:04Z"), "" + expected,
        "2013-11-09T13:10:04Z");
});

test("hatta._pad2", function (assert) {
    assert.strictEqual(hatta._pad2(1), "01", "Single digit.");
    assert.strictEqual(hatta._pad2(10), "10", "Double digit.");
    assert.strictEqual(hatta._pad2(100), "00", "Triple digit.");
});

test("hatta._format_date", function (assert) {
    assert.strictEqual(
        hatta._format_date(new Date("Sat Nov 09 2013 13:10:04 GMT+0100 (CET)")),
        "2013-11-09 13:10 GMT+1", "2013-11-09 13:10:04 GMT+1");
});

test("hatta._foreach_tag", function (assert) {
    var count = 0;
    hatta._foreach_tag(['ins', 'del'], function (tag) {
        count += 1;
    });
    assert.strictEqual(count, 4, "4 <ins> and <del> tags");
});
