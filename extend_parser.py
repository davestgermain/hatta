#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
An example of how you can extend Hatta's parser without touching the
original code.
"""
import hatta
import re

class MyWikiParser(hatta.WikiParser):
    """Alternative WikiParser that uses smilies with noses."""
    smilies = {
        r':-)': "smile.png",
        r':-(': "frown.png",
        r':-P': "tongue.png",
        r':-D': "grin.png",
        r';-)': "wink.png",
    }
    markup = {
        "bold": ur"[*][*]",
        "code": ur"[{][{][{](?P<code_text>([^}]|[^}][}]|[^}][}][}])"
                ur"*[}]*)[}][}][}]",
        "free_link": ur"""(http|https|ftp)://\S+[^\s.,:;!?()'"=+<>-]""",
        "italic": ur"//",
        "link": ur"\[\[(?P<link_target>([^|\]]|\][^|\]])+)"
                ur"(\|(?P<link_text>([^\]]|\][^\]])+))?\]\]",
        "image": hatta.WikiParser.image_pat,
        "linebreak": ur"\\\\",
        "macro": ur"[<][<](?P<macro_name>\w+)\s+"
                 ur"(?P<macro_text>([^>]|[^>][>])+)[>][>]",
        "mail": ur"""(mailto:)?\S+@\S+(\.[^\s.,:;!?()'"/=+<>-]+)+""",
        "math": ur"\$\$(?P<math_text>[^$]+)\$\$",
        "newline": ur"\n",
        "punct": ur'(^|\b|(?<=\s))('+ur"|".join(re.escape(k) for k in hatta.WikiParser.punct)+ur')((?=[\s.,:;!?)/&=+])|\b|$)',
        "smiley": ur"(^|\b|(?<=\s))(?P<smiley_face>%s)((?=[\s.,:;!?)/&=+-])|$)"
                  % ur"|".join(re.escape(k) for k in smilies),
        "text": ur".+?",
    } # note that the priority is alphabetical

hatta.WikiParser = MyWikiParser
hatta.main()

