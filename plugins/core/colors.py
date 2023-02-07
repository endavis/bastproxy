"""
This plugin handles colors

## Color Codes
### Ansi

|| color   ||   regular   ||     bold     ||
|| Red     ||   @r@@r@w   ||     @R@@R@w  ||
|| Green   ||   @g@@g@w   ||     @g@@G@w  ||
|| Yellow  ||   @y@@y@w   ||     @Y@@Y@w  ||
|| Blue    ||   @b@@b@w   ||     @B@@B@w  ||
|| Magenta ||   @m@@m@w   ||     @M@@M@w  ||
|| Cyan    ||   @c@@c@w   ||     @C@@C@w  ||
|| White   ||   @w@@w@w   ||     @W@@W@w  ||

### xterm 256

* @x154@@x154 - make text color xterm 154@w
* @z154@@z154@w - make background color xterm 154@w

"""
# Standard Library
import re

# 3rd Party

# Project
import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'Ansi Colors'
SNAME = 'colors'
PURPOSE = 'Ansi color functions'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

# for finding ANSI color sequences
XTERM_COLOR_REGEX = re.compile(r'^@[xz](?P<num>[\d]{1,3})$')
ANSI_COLOR_REGEX = re.compile(chr(27) + r'\[(?P<arg_1>\d+)(;(?P<arg_2>\d+)' \
                                              r'(;(?P<arg_3>\d+))?)?m')

COLORCODE_REGEX = re.compile(r'(@[cmyrgbwCMYRGBWD|xz[\d{0:3}]])(?P<stuff>.*)')

CONVERTANSI = {}

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
    'x' : '0',
}

COLORTABLE = {}
def build_color_table():
    """
    colors 0..15: 16 basic colors
    """
    COLORTABLE[0] = (0x00, 0x00, 0x00) # 0
    COLORTABLE['k'] = COLORTABLE[0]
    COLORTABLE[1] = (0xcd, 0x00, 0x00) # 1
    COLORTABLE['r'] = COLORTABLE[1]
    COLORTABLE[2] = (0x00, 0xcd, 0x00) # 2
    COLORTABLE['g'] = COLORTABLE[2]
    COLORTABLE[3] = (0xcd, 0xcd, 0x00) # 3
    COLORTABLE['y'] = COLORTABLE[3]
    COLORTABLE[4] = (0x00, 0x00, 0xee) # 4
    COLORTABLE['b'] = COLORTABLE[4]
    COLORTABLE[5] = (0xcd, 0x00, 0xcd) # 5
    COLORTABLE['m'] = COLORTABLE[5]
    COLORTABLE[6] = (0x00, 0xcd, 0xcd) # 6
    COLORTABLE['c'] = COLORTABLE[6]
    COLORTABLE[7] = (0xe5, 0xe5, 0xe5) # 7
    COLORTABLE['w'] = COLORTABLE[7]
    COLORTABLE[8] = (0x7f, 0x7f, 0x7f) # 8
    COLORTABLE['D'] = COLORTABLE[8]
    COLORTABLE[9] = (0xff, 0x00, 0x00) # 9
    COLORTABLE['R'] = COLORTABLE[9]
    COLORTABLE[10] = (0x00, 0xff, 0x00) # 10
    COLORTABLE['G'] = COLORTABLE[10]
    COLORTABLE[11] = (0xff, 0xff, 0x00) # 11
    COLORTABLE['Y'] = COLORTABLE[11]
    COLORTABLE[12] = (0x5c, 0x5c, 0xff) # 12
    COLORTABLE['B'] = COLORTABLE[12]
    COLORTABLE[13] = (0xff, 0x00, 0xff) # 13
    COLORTABLE['M'] = COLORTABLE[13]
    COLORTABLE[14] = (0x00, 0xff, 0xff) # 14
    COLORTABLE['C'] = COLORTABLE[14]
    COLORTABLE[15] = (0xff, 0xff, 0xff) # 15
    COLORTABLE['W'] = COLORTABLE[15]

    # colors 16..232: the 6x6x6 color cube

    valuerange = (0x00, 0x5f, 0x87, 0xaf, 0xd7, 0xff)

    for i in range(217):
        red = valuerange[(i // 36) % 6]
        green = valuerange[(i // 6) % 6]
        blue = valuerange[i % 6]
        COLORTABLE[i + 16] = ((red, green, blue))

    # colors 233..253: grayscale

    for i in range(1, 22):
        gray = 8 + i * 10
        COLORTABLE[i + 233] = ((gray, gray, gray))

build_color_table()

def convertcolorcodetohtml(colorcode):
    """
    convert a colorcode to an html color
    """
    try:
        colorcode = int(colorcode)
        if colorcode in COLORTABLE:
            #print COLORTABLE[colorcode]
            return '#%.2x%.2x%.2x' % (COLORTABLE[colorcode][0],
                                      COLORTABLE[colorcode][1],
                                      COLORTABLE[colorcode][2])
    except ValueError:
        if colorcode in COLORTABLE:
            return '#%.2x%.2x%.2x' % (COLORTABLE[colorcode][0],
                                      COLORTABLE[colorcode][1],
                                      COLORTABLE[colorcode][2])

    return '#000'

def createspan(color, text):
    """
    create an html span

    color = "@g"
    """
    background = False
    if color[0] == '@':
        if color[1] == 'x':
            ncolor = convertcolorcodetohtml(color[2:])
        elif color[1] == 'z':
            ncolor = convertcolorcodetohtml(color[2:])
            background = True
        else:
            ncolor = convertcolorcodetohtml(color[1])
    else:
        ncolor = convertcolorcodetohtml(color)

    if background:
        return '<span style="background-color:%(COLOR)s">%(TEXT)s</span>' % \
            {'COLOR':ncolor,
             'TEXT':text}

    return '<span style="color:%(COLOR)s">%(TEXT)s</span>' % \
        {'COLOR':ncolor,
         'TEXT':text}

for colorc in CONVERTCOLORS:
    CONVERTANSI[CONVERTCOLORS[colorc]] = colorc

#xterm colors
for xtn in range(0, 256):
    CONVERTANSI['38;5;%d' % xtn] = 'x%d' % xtn
    CONVERTANSI['48;5;%d' % xtn] = 'z%d' % xtn

#backgrounds
for acn in range(40, 48):
    CONVERTANSI['%s' % acn] = CONVERTANSI['48;5;%d' % (acn - 40)]

#foregrounds
for abn in range(30, 38):
    CONVERTANSI['%s' % abn] = CONVERTANSI['0;%d' % abn]

def genrepl(match):
    """
    a general replace function
    """
    return match.group(1)

def fixstring(tstr):
    """
    fix a strings invalid colors
    """
    # Thanks to Fiendish from the aardwolf mushclient package, see
    # http://code.google.com/p/aardwolfclientpackage/

    # fix tildes
    tstr = re.sub(r"@-", "~", tstr)
    # change @@ to \0
    tstr = re.sub(r"@@", "\0", tstr)
    # strip invalid xterm codes (non-number)
    tstr = re.sub(r"@[xz]([^\d])", genrepl, tstr)
    # strip invalid xterm codes (300+)
    tstr = re.sub(r"@[xz][3-9]\d\d", "", tstr)
    # strip invalid xterm codes (260+)
    tstr = re.sub(r"@[xz]2[6-9]\d", "", tstr)
    # strip invalid xterm codes (256+)
    tstr = re.sub(r"@[xz]25[6-9]", "", tstr)
    # rip out hidden garbage
    tstr = re.sub(r"@[^xzcmyrgbwCMYRGBWD]", "", tstr)
    return tstr

class Plugin(BasePlugin):
    """
    a plugin to handle ansi colors
    """
    def __init__(self, *args, **kwargs):
        BasePlugin.__init__(self, *args, **kwargs)

        # convert to easier to read api
        self.api('libs.api:add')('colorcode:is:valid', self._api_is_color)
        self.api('libs.api:add')('colorcode:to:ansicode', self._api_convert_colors)
        self.api('libs.api:add')('colorcode:to:html', self._api_colorcodes_to_html)
        self.api('libs.api:add')('colorcode:strip', self._api_strip_color)
        self.api('libs.api:add')('ansicode:to:colorcode', self._api_convert_ansi)
        self.api('libs.api:add')('ansicode:to:string', self._api_ansicode)
        self.api('libs.api:add')('ansicode:strip', self._api_strip_ansi)
        self.api('libs.api:add')('color:length:difference', self._api_length_difference)

        self.dependencies = ['core.commands']

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        parser = argp.ArgumentParser(add_help=False,
                                     description='show colors')
        self.api('core.commands:command:add')('show',
                                              self.cmd_show,
                                              parser=parser)
        parser = argp.ArgumentParser(add_help=False,
                                     description='show color examples')
        self.api('core.commands:command:add')('example',
                                              self.cmd_example,
                                              parser=parser)

    # convert color codes to html
    def _api_colorcodes_to_html(self, sinput):
        # pylint: disable=no-self-use,too-many-branches
        """
        convert colorcodes to html
        """
        tinput = sinput.split('\n')

        olist = []
        for line in tinput:
            if line and line[-1] == '\n':
                lastchar = '\n'
            else:
                lastchar = ''

            line = line.rstrip()
            #line = fixstring(line)
            if '@@' in line:
                line = line.replace('@@', '\0')
            tlist = re.split(r'(@[cmyrgbwCMYRGBWD]|@[xz]\d\d\d|@[xz]\d\d|@[xz]\d)', line)

            nlist = []
            color = 'w'
            tstart = 0
            tend = 0

            for i in range(0, len(tlist)):
                #print 'checking %s, i = %s' % (tlist[i], i)
                if tlist[i]:
                    if tlist[i][0] == '@' and tlist[i][1] in 'xzcmyrgbwCMYRGBWD':
                        #print 'found color'
                        words = tlist[tstart:tend]
                        if color not in ['x', 'D', 'w']:
                            #print 'would put %s in a %s span' % (words, color)
                            nlist.append(createspan(color, ''.join(words)))
                        else:
                            #print 'would just add %s' % words
                            nlist.append(''.join(words))
                        if tlist[i][1] in ['x', 'z']:
                            color = tlist[i]
                        else:
                            color = tlist[i]
                        tstart = i + 1
                        tend = i + 1
                    else:
                        tend = tend + 1
                else:
                    tend = tend + 1
                if i == len(tlist) - 1:
                    words = tlist[tstart:]
                    if color not in ['x', 'D', 'w']:
                        #print 'would put %s in a %s span' % (words, color)
                        nlist.append(createspan(color, ''.join(words)))
                    else:
                        #print 'would just add %s' % words
                        nlist.append(''.join(words))
            tstring = ''.join(nlist)
            if '\0' in tstring:
                tstring = tstring.replace('\0', '@')

            olist.append(tstring + lastchar)

        return '\n'.join(olist) + lastchar

    # get the length difference of a colored string and its noncolor equivalent
    def _api_length_difference(self, colorstring):
        """
        get the length difference of a colored string and its noncolor equivalent
        """
        lennocolor = len(self.api('%s:colorcode:strip' % self.plugin_id)(colorstring))
        lencolor = len(colorstring)
        return lencolor - lennocolor

    # check if a string is an @@ color, either xterm or ansi
    def _api_is_color(self, color):
        # pylint: disable=no-self-use
        """
        check if a string is a @ color, either xterm or ansi
        """
        if re.match(r'^@[cmyrgbwCMYRGBWD]$', color):
            return True
        else:
            mat = XTERM_COLOR_REGEX.match(color)
            if mat:
                num = int(mat.groupdict()['num'])
                if num >= 0 and num < 257:
                    return True

        return False

    # convert @@ colors in a string
    def _api_convert_colors(self, tstr):
        """
        convert @ colors in a string
        """
        test = False
        if '@' in tstr:
            if tstr[-2:] != '@w':
                tstr = tstr + '@w'
            tstr = fixstring(tstr)
            #if test:
                #print 'After fixstring', tstr
            tstr2 = ''
            tmat = re.search(r"@(\w)([^@]+)", tstr)
            if tmat and tmat.start() != 0:
                tstr2 = tstr[0:tmat.start()]
            for tmatch in re.finditer(r"@(\w)([^@]+)", tstr):
                color, text = tmatch.groups()
                if color == 'x':
                    tcolor, newtext = re.findall(r"^(\d\d?\d?)(.*)$", text)[0]
                    color = '38;5;%s' % tcolor
                    tstr2 = tstr2 + self._api_ansicode(color, newtext)
                elif color == 'z':
                    tcolor, newtext = re.findall(r"^(\d\d?\d?)(.*)$", text)[0]
                    color = '48;5;%s' % tcolor
                    tstr2 = tstr2 + self._api_ansicode(color, newtext)
                else:
                    tstr2 = tstr2 + self._api_ansicode(CONVERTCOLORS[color], text)

            if tstr2:
                tstr = tstr2 + "%c[0m" % chr(27)
            if test:
                print(f"After: {tstr}")
        else:
            pass
        tstr = re.sub("\0", "@", tstr)    # put @ back in
        return tstr

    # convert ansi color escape sequences to @@ colors
    def _api_convert_ansi(self, text):
        # pylint: disable=no-self-use
        """
        convert ansi color escape sequences to @@ colors
        """
        def single_sub(match):
            """
            do a single substitution
            """
            argsdict = match.groupdict()
            tstr = ''
            tstr = tstr + argsdict['arg_1']
            if argsdict['arg_2']:
                tstr = tstr + ';%d' % int(argsdict['arg_2'])

            if argsdict['arg_3']:
                tstr = tstr + ';%d' % int(argsdict['arg_3'])

            try:
                return '@%s' % CONVERTANSI[tstr]
            except KeyError:
                print(f"could not lookup color {tstr} for text {repr(text)}")

        return ANSI_COLOR_REGEX.sub(single_sub, text)

    # return an ansi coded string
    def _api_ansicode(self, color, data):
        # pylint: disable=no-self-use
        """
        return an ansi coded string
        """
        return "%c[%sm%s" % (chr(27), color, data)

    # strip all ansi from a string
    def _api_strip_ansi(self, text):
        # pylint: disable=no-self-use
        """
        strip all ansi from a string
        """
        return ANSI_COLOR_REGEX.sub('', text)

    # strip @@ colors from a string
    def _api_strip_color(self, text):
        """
        strip @@ colors
        """
        return self._api_strip_ansi(self._api_convert_colors(text))

    def cmd_show(self, args):
        # pylint: disable=no-self-use
        """
        @G%(name)s@w - @B%(cmdname)s@w
          Show xterm colors
          @CUsage@w: show @Y"compact"@w
            @Y"compact"@w    = The original string to be replaced
        """
        message = ['']
        row_message = []
        compact = False
        joinc = ' '
        if 'compact' in args:
            compact = True
            colors = '@z%s  @w'
            joinc = ''
        else:
            colors = '@B%-3s : @z%s    @w'
        for i in range(0, 16):
            if i % 8 == 0 and i != 0:
                message.append(joinc.join(row_message))
                row_message = []

            if compact:
                row_message.append(colors % (i))
            else:
                row_message.append(colors % (i, i))

        row_message.append('\n')
        message.append(joinc.join(row_message))

        row_message = []

        for i in range(16, 256):
            if (i - 16) % 36 == 0 and ((i - 16) != 0 and not i > 233):
                row_message.append('\n')

            if (i - 16) % 6 == 0 and (i - 16) != 0:
                message.append(joinc.join(row_message))
                row_message = []

            if compact:
                row_message.append(colors % (i))
            else:
                row_message.append(colors % (i, i))

        message.append(joinc.join(row_message))
        row_message = []

        message.append('')

        return True, message


    def cmd_example(self, _=None):
        # pylint: disable=no-self-use
        """
        @G%(name)s@w - @B%(cmdname)s@w
          Show examples of how to use colors
          @CUsage@w: example
        """
        message = ['']
        message.append('Examples')
        message.append('Raw   : @@z165Regular text with color 165 Background@@w')
        message.append('Color : @z165Regular text with color 165 Background@w')
        message.append('Raw   : @@x165@zcolor 165 text with regular Background@@w')
        message.append('Color : @x165color 165 text with regular Background@w')
        message.append('Raw   : @@z255@@x0color 0 text with color 255 Background@@w')
        message.append('Color : @z255@x0color 0 text with color 255 Background@w')
        message.append('Note: see the show command to show the table of colors')
        message.append('')
        return True, message
