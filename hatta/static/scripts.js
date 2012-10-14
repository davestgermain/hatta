(function () {

var parse_date = function (text) {
    /* Parse an ISO 8601 date string. */

    var m = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/.exec(text);
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
};

var format_date = function (d) {
    /* Format a date for output. */

    var pad  = function(number) {
        return ('00' + number).slice(-2);
    };
    var tz = -d.getTimezoneOffset() / 60;
    if (tz >= 0) {
        tz = "+" + tz;
    };
    return ("" + d.getFullYear() + "-" +
            pad(d.getMonth() + 1) + "-" + 
            pad(d.getDate()) + " " +
            pad(d.getHours()) + ":" +
            pad(d.getMinutes()) + " " +
            "GMT" + tz);
};

var localize_dates = function () {
    /* Scan whole document for UTC dates and replace them with
     * local time versions */

    var nodes = document.getElementsByTagName('abbr');
    for (var i=0, len=nodes.length; i < len; ++i) {
        var node = nodes[i];
        if (node.className === 'date') {
            var d = parse_date(node.getAttribute('title'));
            if (d) {
                node.textContent = format_date(d);
            };
        };
    };
};

var js_editor = function () {
    /* Make double click invoke the editor and scroll it to the right place. */

    var textBox = document.getElementById('hatta-editortext');
    if (textBox) {
        /* We have an editor, so scroll it to the right place. */
        var jumpLine = 0 + document.location.hash.substring(1);
        var textLines = textBox.textContent.match(/(.*\n)/g);
        var scrolledText = '';
        for (var i=0, len=textLines.length; i < len && i < jumpLine; ++i) {
            scrolledText += textLines[i];
        }
        /* Put the cursor in the right place. */
        textBox.focus();
        if (textBox.setSelectionRange) {
            textBox.setSelectionRange(scrolledText.length, scrolledText.length);
        } else if (textBox.createTextRange) {
            var range = textBox.createTextRange();
            range.collapse(true);
            range.moveEnd('character', scrolledText.length);
            range.moveStart('character', scrolledText.length);
            range.select();
        }
        /* Determine the height of our text. */
        var scrollPre = document.createElement('pre');
        textBox.parentNode.appendChild(scrollPre);
        var style = window.getComputedStyle(textBox, '');
        scrollPre.style.font = style.font;
        scrollPre.style.border = style.border;
        scrollPre.style.outline = style.outline;
        scrollPre.style.lineHeight = style.lineHeight;
        scrollPre.style.letterSpacing = style.letterSpacing;
        scrollPre.style.fontFamily = style.fontFamily;
        scrollPre.style.fontSize = style.fontSize;
        scrollPre.style.padding = 0;
        scrollPre.style.overflow = 'scroll';
        try { scrollPre.style.whiteSpace = "-moz-pre-wrap" } catch(e) {};
        try { scrollPre.style.whiteSpace = "-o-pre-wrap" } catch(e) {};
        try { scrollPre.style.whiteSpace = "-pre-wrap" } catch(e) {};
        try { scrollPre.style.whiteSpace = "pre-wrap" } catch(e) {};
        scrollPre.textContent = scrolledText;
        /* Scroll our editor to the right place. */
        textBox.scrollTop = scrollPre.scrollHeight;
        scrollPre.parentNode.removeChild(scrollPre);
    } else {
        /* We have a normal page, make it go to editor on double click. */
        var baseUrl = '';
        var tags = document.getElementsByTagName('link');
        for (var i=0, len=tags.length; i < len; ++i) {
            var tag = tags[i];
            if (tag.getAttribute('type') === 'application/wiki') {
                baseUrl = tag.getAttribute('href');
            }
        }
        if (baseUrl==='') {
            return;
        }
        var tagList = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre',
                       'ul', 'div'];
        var dblclick = function () {
            /* The callback that invokes the editor. */
            var url = baseUrl + '#' + this.id.replace('line_', '');
            document.location = url;
            return false;
        };
        for (var j=0, len=tagList.length; j < len; ++j) {
            var tags = document.getElementsByTagName(tagList[j]);
            for (var i=0, len2=tags.length; i < len2; ++i) {
                var tag = tags[i];
                if (tag.id && tag.id.match(/^line_\d+$/)) {
                    tag.ondblclick = dblclick;
                };
            };
        };
    };
};

var purple_numbers = function () {
    /* Add links to the headings. */

    var tagList = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'];
    for (var j=0, len=tagList.length; j < len; ++j) {
        var tags = document.getElementsByTagName(tagList[j]);
        for (var i=0, len2=tags.length; i < len2; ++i) {
            var tag = tags[i];
            var prev = tag.previousSibling;
            while (prev && !prev.tagName) {
                prev = prev.previousSibling;
            };
            if (prev && prev.tagName === 'A') {
                var name = prev.getAttribute('name');
                if (name) {
                    tag.insertAdjacentHTML('beforeend', '<a href="#' + name +
                        '" class="hatta-purple">&para;</a>');
                };
            };
        };
    };
};

window.onload = function () {
    /* Initialize our scripts when the document loads. */

    localize_dates();
    js_editor();
    purple_numbers();
};

})();
