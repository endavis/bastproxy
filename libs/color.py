"""
$Id$

Color Codes:
xterm 256
@x154 - make text color xterm 154
@z154 - make background color xterm154

regular ansi:
         regular    bold
Red        @r        @R
Green      @g        @G
Yellow     @y        @Y
Blue       @b        @B
Magenta    @m        @M
Cyan       @c        @C
White      @w        @W
Reset      @k        @D


# TODO: get closest color client does not support 256 colors
"""
import re

# for finding ANSI color sequences
ANSI_COLOR_REGEXP = re.compile(chr(27) + '\[[0-9;]*[m]')

CONVERTCOLORS = {
  'k' : '0;30',
  'r' : '0;31',
  'g' : '0;32',
  'y' : '0;33', 
  'b' : '0;34', 
  'm' : '0;35',
  'c' : '0;36',
  'w' : '0;37',
  'D' : '1;30',
  'R' : '1;31',
  'G' : '1;32',
  'Y' : '1;33',
  'B' : '1;34',
  'M' : '1;35',
  'C' : '1;36',
  'W' : '1;37', 
}


def genrepl(m):
  return m.group(1)


def fixstring(tstr):
  # Thanks to Fiendish from the aardwolf mushclient package, see 
  # http://code.google.com/p/aardwolfclientpackage/
  
  tstr = re.sub("@-", "~", tstr)                    # fix tildes
  tstr = re.sub("@@", "\0", tstr)                   # change @@ to \0
  tstr = re.sub("@[xz]([^\d])", genrepl, tstr)      # strip invalid xterm codes (non-number)
  tstr = re.sub("@[xz][3-9]\d\d", "", tstr)         # strip invalid xterm codes (300+)
  tstr = re.sub("@[xz]2[6-9]\d", "", tstr)          # strip invalid xterm codes (260+)
  tstr = re.sub("@[xz]25[6-9]", "", tstr)           # strip invalid xterm codes (256+)
  tstr = re.sub("@[^xzcmyrgbwCMYRGBWD]", "", tstr)  # rip out hidden garbage  
  return tstr


def convertcolors(tstr):
  if '@' in tstr:
    if tstr[-2:] != '@w':
      tstr = tstr + '@w'
    tstr = fixstring(tstr)
    tstr2 = ''
    for tmatch in re.finditer("@(\w)([^@]+)", tstr):
      color, text = tmatch.groups()
      if color == 'x':
        tcolor, newtext = re.findall("^(\d\d?\d?)(.*)$", text)[0]
        color = '38;5;%s' % tcolor
        tstr2 = tstr2 + ansicode(color, newtext)
      elif color == 'z':
        tcolor, newtext = re.findall("^(\d\d?\d?)(.*)$", text)[0]
        color = '48;5;%s' % tcolor
        tstr2 = tstr2 + ansicode(color, newtext)
      else:
        tstr2 = tstr2 + ansicode(CONVERTCOLORS[color], text)
        
    if tstr2:
      tstr = tstr2 + "%c[0m" % chr(27)
  else:
    pass
  tstr = re.sub("\0", "@", tstr)    # put @ back in 
  return tstr

      
def ansicode(color, data):
  return "%c[%sm%s" % (chr(27), color, data)


def strip_ansi(text):
  return ANSI_COLOR_REGEXP.sub('', text)
