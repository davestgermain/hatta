##############################################################################
#
# This module has been adapted from ejSplitter.
#
##############################################################################
#
# Copyright (c) 2003-2004 Hajime Nakagami<nakagami@da2.so-net.ne.jp>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. The name of the author may not be used to endorse or promote products 
#    derived from this software without specific prior written permission. 
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
##############################################################################


#Zenkaku -> Hankaku convert table.
conv_tbl = {}
for ch in range(0xFF10, 0xFF1A): # number
    conv_tbl[unichr(ch)] = unichr(ch - 0xFF10 + 0x0030)
for ch in range(0xFF21, 0xFF3B): # upper
    conv_tbl[unichr(ch)] = unichr(ch - 0xFF21 + 0x0041)
for ch in range(0xFF41, 0xFF5B): # lower
    conv_tbl[unichr(ch)] = unichr(ch - 0xFF41 + 0x0061)

#Character class
DELM = -1       # delimiter
KANJI = 0       # kanji
ALNUM = 1       # alfabet number (ASCII/JIS X201)
HAN_KANA = 2    # katakana (JIS X201)
ZEN_ALNUM = 3   # alfabet number(JIS X208)
ZEN_KANA = 4    # katakana (JISX 208)
ZEN_HIRA = 5    # hiragana (JISX 208)
ZEN_DEPEND = 6  # context dependent zenkaku character

#Character -> Character class mapping
char_class = {}

#DELM
 #JIS X 201 LH
delm_codes = range(0x20, 0x30) + range(0x3A, 0x41) + range(0x5B, 0x61) + \
            [0x7B, 0x7C, 0x7D, 0x203E]
 #JIS X 201 RH
delm_codes += range(0xFF61, 0xFF66)
 #JIS X 208
delm_codes += [0x3000, 0x3001, 0x3002, 0xFF0C, 0xFF0E, 0x30FB, 0xFF1A,
               0xFF1B, 0xFF1F, 0xFF01, 0x309B, 0x309C, 0x00B4, 0xFF40,
               0x00A8, 0xFF3E, 0xFFE3, 0xFF3F] + \
              [0xFF0F, 0x005C, 0x301C, 0x2016, 0xFF5C, 0x2026, 0x2025,
               0x2018, 0x2019, 0x201C, 0x201D, 0xFF08, 0xFF09, 0x3014,
               0x3015, 0xFF3B, 0xFF3D, 0xFF5B, 0xFF5D, 0x3008, 0x3009,
               0x300A, 0x300B, 0x300C, 0x300D, 0x300E, 0x300F, 0x3010,
               0x3011, 0xFF0B, 0x2212, 0x00B1, 0x00D7, 0x00F7, 0xFF1D,
               0x2260, 0xFF1C, 0xFF1E, 0x2266, 0x2267, 0x221E, 0x2234,
               0x2642, 0x2640, 0x00B0, 0x2032, 0x2033, 0x2103, 0xFFE5,
               0xFF04, 0x00A2, 0x00A3, 0xFF05, 0xFF03, 0xFF06, 0xFF0A,
               0xFF20, 0x00A7, 0x2606, 0x2605, 0x25CB, 0x25CF, 0x25CE,
               0x25C7, 0x25C6, 0x25A1, 0x25A0, 0x25B3, 0x25B2, 0x25BD,
               0x25BC, 0x203B, 0x3012, 0x2192, 0x2190, 0x2191, 0x2193,
               0x3013] + \
              [0x2208, 0x220B, 0x2286, 0x2287, 0x2282, 0x2283, 0x222A,
               0x2229] + \
              [0x2227, 0x2228, 0x00AC, 0x21D2, 0x21D4, 0x2220, 0x2203] + \
              [0x2220, 0x22A5, 0x2312, 0x2202, 0x2207, 0x2261, 0x2252,
               0x226A, 0x226B, 0x221A, 0x223D, 0x221D, 0x2235, 0x222B,
               0x222C] + \
              [0x212B, 0x2030, 0x266F, 0x266D, 0x266A, 0x2020, 0x2021,
               0x00B6, 0x25FE] + \
              [0x2500, 0x2502, 0x250C, 0x2510, 0x2518, 0x2514, 0x251C,
               0x252C, 0x2524, 0x2534, 0x253C, 0x2501, 0x2503, 0x250F,
               0x2513, 0x251B, 0x2517, 0x2523, 0x252B, 0x253B, 0x254B,
               0x2520, 0x252F, 0x2528, 0x2537, 0x253F, 0x251D, 0x2530,
               0x2525, 0x2538, 0x2542]

for chcode in delm_codes:
    char_class[unichr(chcode)] = DELM

#ALNUM
alnum_codes = range(0x30, 0x3A) + range(0x41, 0x5B) + range(0x61, 0x7B)
for chcode in alnum_codes:
    char_class[unichr(chcode)] = ALNUM

#HAN_KANA
han_kana_codes = range(0xFF66, 0xFF9F)
for chcode in han_kana_codes:
    char_class[unichr(chcode)] = HAN_KANA

#ZEN_ALNUM
zen_alnum_codes = range(0xFF10, 0xFF1A) # number
zen_alnum_codes += range(0xFF21, 0xFF3B) + range(0xFF41, 0xFF5B) # alfabet 
zen_alnum_codes += range(0x0391, 0x03AA) + range(0x03B1, 0x03CA) # greek
zen_alnum_codes += range(0x0410, 0x0430) + range(0x0430, 0x0450) # cyrilic
for chcode in zen_alnum_codes:
    char_class[unichr(chcode)] = ZEN_ALNUM


#ZEN_HIRA
zen_hira_codes = range(0x3041, 0x3094)
for chcode in zen_hira_codes:
    char_class[unichr(chcode)] = ZEN_HIRA

#ZEN_KANA
zen_kana_codes = range(0x30A1, 0x30F7)
for chcode in zen_kana_codes:
    char_class[unichr(chcode)] = ZEN_KANA

#ZEN_DEPEND
depend_codes = [0xFF5E, 0x30FC]
for chcode in depend_codes:
    char_class[unichr(chcode)] = ZEN_DEPEND

def convert_char(ch):
    return conv_tbl.get(ch, ch)

def guess_charclass(ch):
    return char_class.get(ch, KANJI)

def split_japanese(utext, glob):
    char_state = DELM
    word = u''
    for ch in utext:
        ch = convert_char(ch)
        if glob and char_state != DELM and (ch == u'*' or ch == u'?'):
            word += ch
            continue
        new_state = guess_charclass(ch)
        if new_state == ZEN_DEPEND:
            if char_state == ZEN_KANA or char_state == ZEN_HIRA:
                new_state = char_state
            else:
                new_state = DELM
        if new_state == DELM:
            if char_state != DELM:
                yield word
                word = u''
                char_state = DELM
        elif new_state != char_state:
            if char_state != DELM:
                yield word
                word = u''
            word += ch
            char_state = new_state
        else:
            word += ch
    if char_state != DELM:
            yield word
