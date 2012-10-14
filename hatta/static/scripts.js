function hatta_dates(){var a=document.getElementsByTagName(
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
window.onload=function(){hatta_dates();hatta_edit()}
