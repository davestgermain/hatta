var hatta = function () {
    var hatta = {};

    hatta._parse_date = function (text) {
        /* Parse an ISO 8601 date string. */

        var m = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/.exec(text);
        return new Date(
            Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
    };

    hatta._pad2  = function(number) {
        /* Pad a number with zeroes. The result always has 2 digits. */

        return ('00' + number).slice(-2);
    };

    hatta._format_date = function (d) {
        /* Format a date for output. */

        var tz = -d.getTimezoneOffset() / 60;
        if (tz >= 0) {
            tz = "+" + tz;
        }
        return ("" + d.getFullYear() + "-" +
                hatta._pad2(d.getMonth() + 1) + "-" + 
                hatta._pad2(d.getDate()) + " " +
                hatta._pad2(d.getHours()) + ":" +
                hatta._pad2(d.getMinutes()) + " " +
                "GMT" + tz);
    };

    hatta._foreach_tag = function (tag_names, func) {
        tag_names.forEach(function (tag_name) {
            Array.prototype.forEach.call(
                document.getElementsByTagName(tag_name), func);
        });
    };

    hatta.localize_dates = function () {
        /* Scan whole document for UTC dates and replace them with
         * local time versions */

        hatta._foreach_tag(['abbr'], function (tag) {
            if (tag.className === 'date') {
                var d = _parse_date(node.getAttribute('title'));
                if (d) {
                    tag.textContent = _format_date(d);
                }
            }
        });
    };

    hatta.js_editor = function () {
        /* Make double click invoke the editor and scroll it to the right
         * place. */

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
                textBox.setSelectionRange(scrolledText.length,
                                          scrolledText.length);
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
            try { scrollPre.style.whiteSpace = "-moz-pre-wrap"; } catch(e) {}
            try { scrollPre.style.whiteSpace = "-o-pre-wrap"; } catch(e) {}
            try { scrollPre.style.whiteSpace = "-pre-wrap"; } catch(e) {}
            try { scrollPre.style.whiteSpace = "pre-wrap"; } catch(e) {}
            scrollPre.textContent = scrolledText;
            /* Scroll our editor to the right place. */
            textBox.scrollTop = scrollPre.scrollHeight;
            scrollPre.parentNode.removeChild(scrollPre);
        } else {
            /* We have a normal page, make it go to editor on double click. */
            var baseUrl = '';
            hatta._foreach_tag(['link'], function (tag) {
                if (tag.getAttribute('type') === 'application/wiki') {
                    baseUrl = tag.getAttribute('href');
                }
            });
            if (baseUrl==='') {
                return;
            }
            var dblclick = function () {
                /* The callback that invokes the editor. */
                var url = baseUrl + '#' + this.id.replace('line_', '');
                document.location = url;
                return false;
            };
            hatta._foreach_tag(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'ul',
                          'div'], function (tag) {
                if (tag.id && tag.id.match(/^line_\d+$/)) {
                    tag.ondblclick = dblclick;
                }
            });
        }
    };

    hatta.purple_numbers = function () {
        /* Add links to the headings. */

        hatta._foreach_tag(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], function (tag) {
            var prev = tag.previousSibling;
            while (prev && !prev.tagName) {
                prev = prev.previousSibling;
            }
            if (prev && prev.tagName === 'A') {
                var name = prev.getAttribute('name');
                if (name) {
                    tag.insertAdjacentHTML('beforeend', '<a href="#' +
                        name + '" class="hatta-purple">&para;</a>');
                }
            }
        });
    };

    hatta.toc = function () {
        var tags = [];
        hatta._foreach_tag(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], function (tag) {
            if (tag.getAttribute('id')) {
                tags.push(tag);
            }
        });
        tags.sort(function (a, b) {
            /* Sort according to line numbers from id="line_X" attributes. */
            return a.getAttribute('id').slice(5) - b.getAttribute('id').slice(5);
        });
        console.log(tags);
    };

    return hatta;
}();

window.onload = function () {
    /* Initialize our scripts when the document loads. */

    hatta.localize_dates();
    hatta.js_editor();
    hatta.purple_numbers();
};
