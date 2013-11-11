test("hatta._pad2", function () {
    strictEqual(hatta._pad2(1), "01", "Single digit.");
    strictEqual(hatta._pad2(10), "10", "Double digit.");
    strictEqual(hatta._pad2(100), "00", "Triple digit.");
});
