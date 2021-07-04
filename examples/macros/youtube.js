/*
This macro looks like:
<<yt abcXyZ>>
where abcXyZ is the youtube video id.

You can set the width and height after the id
<<yt abcXyZ 640 480>>
*/

hatta.register_macro('yt', function(elt) {
    var width = 550;
    var height = 310;
    var sp = elt.innerText.split(" ");
    var ytId = sp[0];
    if (sp.length > 1) {
        width = sp[1];
        height = sp[2];
    }
    var embed = '<iframe width="' + width + '" height="' + height + '" src="https://www.youtube.com/embed/' + ytId + '" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>';
    elt.innerHTML = embed;
});
