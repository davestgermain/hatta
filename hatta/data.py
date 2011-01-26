#!/usr/bin/python
# -*- coding: utf-8 -*-

import base64


icon = base64.b64decode(
'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhki'
'AAAAAlwSFlzAAAEnQAABJ0BfDRroQAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBo'
'AAALWSURBVDiNbdNLaFxlFMDx//fd19x5JdNJm0lIImPaYm2MfSUggrssXBVaChUfi1JwpQtxK7gqu'
'LMbQQQ3bipU0G3Rgg98DBpraWob00kzM6Z5TF7tdObm3vvd46K0TBo/OLtzfnychxIRut+Zo2/19vT'
'kLxXze6biONbGJMRipL39MJyt33rvp+rVT7rzVTfw2vFzLxwcLf/V7oSq1W4hACIkIigUtnaoNecXG'
'2u14T8blQRAd2v7yyN/RLFR6IRM1iedSeFnUvhpDydlI9ow0lcedG3348c1djeQz+WcThjgYZMgGBG'
'SJMEYgzGGODLEoTBYGH4DeHcXoDSSzaRVogQjyaMwhtgYcoUco+Nl5qbnubFw7fr//uB2tXp78uj4c'
'0YJsSTESUxsDCemjjH6YhnbtbA8xaVv7n/0uGZHDx48aH8+17iLJQrf9vCdFL7tkcn7/Pb7r8zdmWP'
'2zqwopa7sAl4/cV4NlvrPbgch7aBN1vUIOw9ZWmmw2dqkb18fQSegOrOgfD9zahfQ37/3su+ljj1T6'
'uCnAyxtoZVGa41tWSilULWfCZdaPD986MsjQxOHdwC9PdmT2tLk0oozpxfYf2SZwp4Iz1X4UZWBe1+'
'z9+5X+OkiruWpYr744ZMmvjn5dvrwoVHLdRzWtobY2Kwx9soyz5ZXuV9fQ5pXCBabXKuXcBwbYwxYe'
'kIppTXAF5VP2xutrVYmm8bzM1z9foSZik1z1SWMNLW1AtMrB/gnnMJxbSxbUV2a/QHQT8Y4c+vvC8V'
'C74VCoZcodvnxux5Msg+THCSKHy2R48YgIb/crITrreZlEYl33MKrYycvvnx88p2BUkkpRyGSEBmDi'
'WI6QcC95UUqM9PBzdqN99fbzc9EJNwBKKUoFw+8NDY8/sFQ/8CE57l5pZRdX6kHqxurW43mv98urM9'
'fjJPouohE8NQ1dkEayAJ5wAe2gRawJSKmO/c/aERMn5m9/ksAAAAASUVORK5CYII=')

scripts = r"""function hatta_dates(){var a=document.getElementsByTagName(
'abbr');var p=function(i){return('00'+i).slice(-2)};for(var i=0;i<a.length;++i)
{var n=a[i];if(n.className==='date'){var m=
/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/.exec(
n.getAttribute('title'));var d=new Date(Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],
+m[5],+m[6]));if(d){var b=-d.getTimezoneOffset()/60;if(b>=0){b="+"+b}
n.textContent=""+d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+
p(d.getHours())+":"+p(d.getMinutes())+" GMT"+b}}}}function hatta_edit(){var b=
document.getElementById('editortext');if(b){var c=0+
document.location.hash.substring(1);var d=b.textContent.match(/(.*\n)/g);var
f='';for(var i=0;i<d.length&&i<c;++i){f+=d[i]}b.focus();if(b.setSelectionRange)
{b.setSelectionRange(f.length,f.length)}else if(b.createTextRange){var g=
b.createTextRange();g.collapse(true);g.moveEnd('character',f.length);
g.moveStart('character',f.length);g.select()}var h=document.createElement('pre'
);b.parentNode.appendChild(h);var k=window.getComputedStyle(b,'');h.style.font=
k.font;h.style.border=k.border;h.style.outline=k.outline;h.style.lineHeight=
k.lineHeight;h.style.letterSpacing=k.letterSpacing;h.style.fontFamily=
k.fontFamily;h.style.fontSize=k.fontSize;h.style.padding=0;h.style.overflow=
'scroll';try{h.style.whiteSpace="-moz-pre-wrap"}catch(e){};try{
h.style.whiteSpace="-o-pre-wrap"}catch(e){};try{h.style.whiteSpace="-pre-wrap"
}catch(e){};try{h.style.whiteSpace="pre-wrap"}catch(e){};h.textContent=f;
b.scrollTop=h.scrollHeight;h.parentNode.removeChild(h)}else{var l='';var m=
document.getElementsByTagName('link');for(var i=0;i<m.length;++i){var n=m[i];
if(n.getAttribute('type')==='application/wiki'){l=n.getAttribute('href')}}if(
l===''){return}var o=['p','h1','h2','h3','h4','h5','h6','pre','ul','div',
'span'];for(var j=0;j<o.length;++j){var m=document.getElementsByTagName(o[j]);
for(var i=0;i<m.length;++i){var n=m[i];if(n.id&&n.id.match(/^line_\d+$/)){
n.ondblclick=function(){var a=l+'#'+this.id.replace('line_','');
document.location.href=a}}}}}}
window.onload=function(){hatta_dates();hatta_edit()}"""

style = """\
html { background: #fff; color: #2e3436;
    font-family: sans-serif; font-size: 96% }
body { margin: 1em auto; line-height: 1.3; width: 40em }
a { color: #3465a4; text-decoration: none }
a:hover { text-decoration: underline }
a.wiki:visited { color: #204a87 }
a.nonexistent, a.nonexistent:visited { color: #a40000; }
a.external { color: #3465a4; text-decoration: underline }
a.external:visited { color: #75507b }
a img { border: none }
img.math, img.smiley { vertical-align: middle }
pre { font-size: 100%; white-space: pre-wrap; word-wrap: break-word;
    white-space: -moz-pre-wrap; white-space: -pre-wrap;
    white-space: -o-pre-wrap; line-height: 1.2; color: #555753 }
div.conflict pre.local { background: #fcaf3e; margin-bottom: 0; color: 000}
div.conflict pre.other { background: #ffdd66; margin-top: 0; color: 000; border-top: #d80 dashed 1px; }
pre.diff div.orig { font-size: 75%; color: #babdb6 }
b.highlight, pre.diff ins { font-weight: bold; background: #fcaf3e;
color: #ce5c00; text-decoration: none }
pre.diff del { background: #eeeeec; color: #888a85; text-decoration: none }
pre.diff div.change { border-left: 2px solid #fcaf3e }
div#hatta-footer { border-top: solid 1px #babdb6; text-align: right }
h1, h2, h3, h4 { color: #babdb6; font-weight: normal; letter-spacing: 0.125em}
div.buttons { text-align: center }
input.button, div.buttons input { font-weight: bold; font-size: 100%;
    background: #eee; border: solid 1px #babdb6; margin: 0.25em; color: #888a85}
.history input.button { font-size: 75% }
.editor textarea { width: 100%; display: block; font-size: 100%;
    border: solid 1px #babdb6; }
.editor label { display:block; text-align: right }
.editor .upload { margin: 2em auto; text-align: center }
form#hatta-search input#hatta-search, .editor label input { font-size: 100%;
    border: solid 1px #babdb6; margin: 0.125em 0 }
.editor label.comment input  { width: 32em }
a#hatta-logo { float: left; display: block; margin: 0.25em }
div#hatta-header h1 { margin: 0; }
div#hatta-content { clear: left }
form#hatta-search { margin:0; text-align: right; font-size: 80% }
div.snippet { font-size: 80%; color: #888a85 }
div#hatta-header div#hatta-menu { float: right; margin-top: 1.25em }
div#hatta-header div#hatta-menu a.current { color: #000 }
hr { background: transparent; border:none; height: 0;
     border-bottom: 1px solid #babdb6; clear: both }
blockquote { border-left:.25em solid #ccc; padding-left:.5em; margin-left:0}
abbr.date {border:none}
dt {font-weight: bold; float: left; }
dd {font-style: italic; }
@media print {
 body {background:white;color:black;font-size:100%;font-family:serif;}
 #hatta-search, #hatta-menu, #hatta-footer {display:none;}
 a:link, a:visited {color:#520;font-weight:bold;text-decoration:underline;}
 #hatta-content {width:auto;}
 #hatta-content a:link:after,
 #hatta-content a:visited:after{content:" ["attr(href)"] ";font-size:90%;}
}
"""

