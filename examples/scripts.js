function localize_dates() {
/* Scan whole document for UTC dates and replace them with localtime versions */
    var parse_date = function (text) {
        var m = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/.exec(text);
        var d = new Date();
        d.setUTCFullYear(+m[1]);
        d.setUTCMonth(+m[2]);
        d.setUTCDate(+m[3]);
        d.setUTCHours(+m[4]);
        d.setUTCMinutes(+m[5]);
        d.setUTCSeconds(+m[6]);
        return d;
    }
    var format_date = function (d) {
        var p = function(n) {return ('00'+n).slice(-2); };
        var tz = d.getTimezoneOffset()/60;
        if (tz>0) { tz = "+"+tz; }
        return ""+d.getFullYear()+"-"+p(d.getMonth())+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes())+" GMT"+tz;
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

window.onload = function () {
    localize_dates();
}

