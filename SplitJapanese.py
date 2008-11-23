#!/usr/bin/python
# -*- coding: utf-8 -*-
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
conv_tbl = {u'１': u'1', u'０': u'0', u'３': u'3', u'２': u'2', u'５': u'5',
u'４': u'4', u'７': u'7', u'６': u'6', u'９': u'9', u'８': u'8', u'Ａ': u'A',
u'Ｃ': u'C', u'Ｂ': u'B', u'Ｅ': u'E', u'Ｄ': u'D', u'Ｇ': u'G', u'Ｆ': u'F',
u'Ｉ': u'I', u'Ｈ': u'H', u'Ｋ': u'K', u'Ｊ': u'J', u'Ｍ': u'M', u'Ｌ': u'L',
u'Ｏ': u'O', u'Ｎ': u'N', u'Ｑ': u'Q', u'Ｐ': u'P', u'Ｓ': u'S', u'Ｒ': u'R',
u'Ｕ': u'U', u'Ｔ': u'T', u'Ｗ': u'W', u'Ｖ': u'V', u'Ｙ': u'Y', u'Ｘ': u'X',
u'Ｚ': u'Z', u'ａ': u'a', u'ｃ': u'c', u'ｂ': u'b', u'ｅ': u'e', u'ｄ': u'd',
u'ｇ': u'g', u'ｆ': u'f', u'ｉ': u'i', u'ｈ': u'h', u'ｋ': u'k', u'ｊ': u'j',
u'ｍ': u'm', u'ｌ': u'l', u'ｏ': u'o', u'ｎ': u'n', u'ｑ': u'q', u'ｐ': u'p',
u'ｓ': u's', u'ｒ': u'r', u'ｕ': u'u', u'ｔ': u't', u'ｗ': u'w', u'ｖ': u'v',
u'ｙ': u'y', u'ｘ': u'x', u'ｚ': u'z'}

#Character class
DELM = -1       # delimiter
KANJI = 0       # kanji
ALNUM = 1       # alfabet number (ASCII/JIS X201)
HAN_KANA = 2    # katakana (JIS X201)
ZEN_ALNUM = 3   # alfabet number(JIS X208)
ZEN_KANA = 4    # katakana (JISX 208)
ZEN_HIRA = 5    # hiragana (JISX 208)
ZEN_DEPEND = 6  # context dependent zenkaku character

delm_set = frozenset(u" !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}‾｡｢｣､･　、。，．・：；"
u"？！゛゜´"
u"｀¨＾￣＿／\\〜‖｜…‥‘’“”（）〔〕［］｛｝〈〉《》「」『』【】＋−±×÷＝≠＜＞≦≧∞∴"
u"♂♀°′″℃￥＄¢£％＃＆＊＠§☆★○●◎◇◆□■△▲▽▼※〒→←↑↓〓∈∋⊆⊇⊂⊃∪∩∧∨¬⇒⇔∠∃∠⊥⌒∂∇≡≒≪≫√∽∝∵∫∬Å‰"
u"♯♭♪†‡¶◾─│┌┐┘└├┬┤┴┼━┃┏┓┛┗┣┫┻╋┠┯┨┷┿┝┰┥┸╂")

def guess_charclass(ch):
    code = ord(ch)
    if 0xFF66 <= code < 0xFF9F:
        return HAN_KANA
    elif 0x3041 <= code < 0x3094:
        return ZEN_HIRA
    elif 0x30A1 <= code < 0x30F7:
        return ZEN_KANA
    elif (0x30 <= code < 0x3A or 0x41 <= code < 0x5B or 0x61 <= code < 0x7B):
        return ZEN_ALNUM
    elif (0xFF10 <= code < 0xFF1A or 0xFF21 <= code < 0xFF3B or
          0xFF41 <= code < 0xFF5B or 0x0391 <= code < 0x03AA or
          0x03B1 <= code < 0X03CA or 0x0410 <= code < 0x0450):
        return ALNUM
    elif ch in delm_set:
        return DELM
    elif code in (0xFF5E, 0x30FC):
        return ZEN_DEPEND
    return KANJI

def split_japanese(utext, glob=None):
    char_state = DELM
    word = []
    for ch in utext:
        ch = conv_tbl.get(ch, ch)
        new_state = guess_charclass(ch)
        if new_state == ZEN_DEPEND:
            if char_state == ZEN_KANA or char_state == ZEN_HIRA:
                new_state = char_state
            else:
                new_state = DELM
        if new_state == DELM:
            if char_state != DELM:
                yield u''.join(word)
                word = []
                char_state = DELM
        elif new_state != char_state:
            if char_state != DELM:
                yield u''.join(word)
                word = []
            word.append(ch)
            char_state = new_state
        else:
            word.append(ch)
    if char_state != DELM:
        yield u''.join(word)
