function hatta_dates() {
/* Scan whole document for UTC dates and replace them with localtime versions */
    var parse_date = function (text) {
        var m = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/.exec(text);
        return new Date(Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]));
    }
    var format_date = function (d) {
        var p = function(n) {return ('00'+n).slice(-2); };
        var tz = -d.getTimezoneOffset()/60;
        if (tz>=0) { tz = "+"+tz; }
        return ""+d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes())+" GMT"+tz;
    }
    var nodes = document.getElementsByTagName('abbr');
    for (var i=0; i<nodes.length; ++i) {
        var node = nodes[i];
        if (node.className === 'date') {
            var d = parse_date(node.getAttribute('title'));
            if (d) {
                node.textContent = format_date(d);
            }
        }
    }
}

function hatta_editor() {
    var textBox = document.getElementById('editortext');
    if (textBox) {
        var jumpLine = 0+document.location.hash.substring(1);
        var textLines = textBox.textContent.match(/(.*\n)/g);
        var scrolledText = '';
        for (var i = 0; i < textLines.length && i < jumpLine; ++i) {
            scrolledText += textLines[i];
        }
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
        textBox.scrollTop = scrollPre.scrollHeight;
        scrollPre.parentNode.removeChild(scrollPre);
    } else {
        var baseUrl = '';
        var tags = document.getElementsByTagName('link');
        for (var i = 0; i < tags.length; ++i) {
            var tag = tags[i];
            if (tag.getAttribute('type')==='application/wiki') {
                baseUrl = tag.getAttribute('href');
            }
        }
        if (baseUrl==='') {
            return;
        }
        var tagList = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'ul', 'div'];
        for (var j = 0; j < tagList.length; ++j) {
            var tags = document.getElementsByTagName(tagList[j]);
            for (var i = 0; i < tags.length; ++i) {
                var tag = tags[i];
                if (tag.id && tag.id.match(/^line_\d+$/)) {
                    tag.ondblclick = function () {
                        var url = baseUrl+'#'+this.id.replace('line_', '');
                        document.location.href = url;
                    };
                }
            }
        }
    }
}

window.onload = function () {
    hatta_dates();
    hatta_editor();
}

