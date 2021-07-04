/*
This macro looks like:
<<redirect http://example.com>>
*/

hatta.register_macro('redirect', function(elt) {
    location.href = elt.innerText;
});
