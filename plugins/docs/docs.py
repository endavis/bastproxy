"""
This module creates the documentation

it requires the markdown2 and lxml libraries
"""
import sys
import os
import copy
import distutils.dir_util as dir_util

try:
  import markdown2
except ImportError:
  markdown2 = None

try:
  import lxml
except ImportError:
  lxml = None

from cgi import escape

import libs.argp as argp
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Documentation'
SNAME = 'docs'
PURPOSE = 'create bastproxy documentation'
AUTHOR = 'Bast'
VERSION = 1

class Plugin(BasePlugin):
  """
  a plugin to create documentation
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    self.themelist = ""

    BasePlugin.__init__(self, *args, **kwargs)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='create documentation')
    self.api('commands.add')('build', self.cmd_build,
                             parser=parser, group='Documentation')


  def import_markdown2(self):
    """
    import the markdown2 module
    """
    global markdown2
    if not markdown2:
      try:
        import markdown2
      except ImportError:
        self.api('send.error')('Please install markdown2 with "pip(2) install markdown2"')
        return False

    return True

  def import_lxml(self):
    """
    import the lxml module
    """
    global lxml
    if not lxml:
      try:
        import lxml
      except ImportError:
        self.api('send.error')('Please install lxml with "pip(2) install lxml"')
        return False

    return True

  def build_themelist(self):
    """
    build a list of themes to pick
    """
    themepath = os.path.join(self.plugin_directory, 'css',
                             'themes')

    template = '<li><a href="#" class="change-style-menu-item" rel="%(rel)s">' \
                  '<i class="icon-fixed-width icon-pencil"></i> %(theme)s</a></li>'

    themelist = os.listdir(themepath)

    tstr = []

    for i in themelist:
      name = os.path.splitext(i)[0].capitalize()
      path = os.path.join("/bastproxy", "css", "themes", i)

      tstr.append(template % {'rel':path, 'theme':name})

    self.themelist = "\n".join(tstr)

  def buildtoc(self, toc):
    """
    convert a toc from markdown
    """
    tocl = []
    tocl.append('<ul class="nav sidebar-fixed">')
    firstlev = toc[0][0]
    tocn = {}
    topparent = tocn
    secparent = {}
    for i in xrange(0, len(toc)):
      level = toc[i][0]
      tid = toc[i][1]
      text = toc[i][2]
      if level == firstlev:
        itemn = len(tocn) + 1
        tocn[itemn] = {}
        tocn[itemn]['id'] = tid
        tocn[itemn]['text'] = text
        tocn[itemn]['parent'] = None
        tocn[itemn]['children'] = {}
        topparent = tocn[itemn]
      elif level == firstlev + 1:
        childn = len(topparent['children']) + 1
        topparent['children'][childn] = {}
        topparent['children'][childn]['id'] = tid
        topparent['children'][childn]['text'] = text
        topparent['children'][childn]['parent'] = topparent
        topparent['children'][childn]['children'] = {}
        secparent = topparent['children'][childn]
      elif level == firstlev + 2:
        childn = len(secparent['children']) + 1
        secparent['children'][childn] = {}
        secparent['children'][childn]['id'] = tid
        secparent['children'][childn]['text'] = text
        secparent['children'][childn]['parent'] = secparent
        secparent['children'][childn]['children'] = {}


    tocl.extend(self.tocitem(tocn))
    return '\n'.join(tocl)

  def tocitem(self, nitem):
    """
    create a table of contents item
    """
    tocl = []
    for i in sorted(nitem.keys()):
      item = nitem[i]
      data_target = item['id'] + 'Menu'
      if item['children']:
        tocl.append(
            """  <li><a href="#" data-toggle="collapse" data-target="#%(data_target)s">
              %(text)s <i class="glyphicon glyphicon-chevron-right"></i>
              <ul class="list-unstyled collapse" id="%(data_target)s">""" % \
                {'data_target':data_target, 'text':item['text']})
        tocl.extend(self.tocitem(item['children']))
        tocl.append('</ul></li>')
      else:
        tocl.append('  <li><a href="#%(id)s">%(text)s</a></li>' % \
          {'id':item['id'], 'text':item['text']})

    return tocl

  @staticmethod
  def checknodocs(plugin):
    """
    check for no docs setting
    """
    ppack = 'plugins.%s' % plugin.package

    if 'NODOCS' not in sys.modules[ppack].__dict__:
      return False
    elif 'NODOCS' in sys.modules[ppack].__dict__:
      return bool(sys.modules[ppack].__dict__['NODOCS'])

    return False

  def buildpluginmenu(self, plugininfo):
    """
    build the plugin menu
    """
    pmenu = []

    ptree = {}
    for i in plugininfo.keys():
      pmod = self.api('plugins.getp')(plugininfo[i]['plugin_path'])

      try:
        sys.modules[pmod.full_import_location].__doc__
      except AttributeError:
        self.api('send.msg')('Plugin %s is not loaded' % \
                                                plugininfo[i]['plugin_path'])
        continue

      moddir = os.path.basename(os.path.split(i)[0])
      name = os.path.splitext(os.path.basename(i))[0]

      if not self.checknodocs(pmod):
        if moddir not in ptree:
          ptree[moddir] = {}

        ptree[moddir][name] = {'location':i}

    for i in sorted(ptree.keys()):
      pmenu.append("""<li class="dropdown-submenu">
            <a href="#" class="dropdown-toggle" data-toggle="dropdown">%s</a>
                  <ul class="dropdown-menu">""" % (i.capitalize()))
      for j in sorted(ptree[i].keys()):
        item = plugininfo[ptree[i][j]['location']]
        pmenu.append('<li><a href="%(link)s">%(name)s</a></li>' % \
                       {'name':item['short_name'],
                        'link':'/bastproxy/plugins/%s/%s.html' % (i, item['short_name'])})
      pmenu.append('</ul>')
      pmenu.append('</li>')

    return '\n'.join(pmenu)

  def build_index(self, title, pluginmenu, _, template):
    """
    build the index page
    """
    #testdoc = __doc__

    testdoc = sys.modules['__main__'].__doc__

    about = markdown2.markdown(testdoc,
                               extras=['header-ids', 'fenced-code-blocks',
                                       'wiki-tables'])

    nbody = self.adddivstodoc(about)

    nbody = self.addhclasses(nbody)

    body = self.addtableclasses(nbody)

    ttoc = self.buildtoc(
        self.gettoc('<body>\n' + '\n'.join(body) + '\n</body>'))

    html = template % {'BODY':'\n'.join(body), 'TOC':ttoc, 'TITLE':title,
                       'PLUGINMENU':pluginmenu, 'PNAME':'Bastproxy', 'CSS':'dark.css',
                       'THEMEMENU':self.themelist}

    tfile = open(os.path.join(self.api.BASEPATH, 'docsout', 'index.html'), 'w')

    tfile.write(html)

    tfile.close()

  @staticmethod
  def addelementclass(html, element, eclass):
    """
    add a class to an element

    eclass can include the tagname as %(tag)s
    """
    from lxml import etree

    if isinstance(html, list):
      html = '\n'.join(html)

    doc = etree.fromstring('<body>\n' + html + '\n</body>\n')
    for node in doc.xpath(element):
      attrib = node.attrib
      nclass = eclass % {'tag':node.tag}
      if attrib.get('class'):
        attrib['class'] = attrib.get('class') + ' ' + nclass
      else:
        attrib['class'] = nclass

    htmlout = etree.tostring(doc, pretty_print=True)

    htmlout = htmlout.strip()

    html = htmlout.split('\n')

    html.remove('<body>')
    html.remove('</body>')

    return html

  def addhclasses(self, html):
    """
    add classes to headers
    """
    return self.addelementclass(html, '//h1|//h2|//h3|//h4|//h5', 'bp%(tag)s')

  def addtableclasses(self, html):
    """
    add classes to tables
    """
    return self.addelementclass(html, '//table', 'table')

  def gettoc(self, html):
    """
    get the toc from the html headers
    """
    from lxml import etree

    toc = []
    try:
      doc = etree.fromstring(html)
      for node in doc.xpath('//h1|//h2|//h3|//h4|//h5'):
        toc.append((int(node.tag[-1]), node.attrib.get('id'), node.text))
    except:
      self.api('send.traceback')('error parsing html')
      print html

    return toc

  @staticmethod
  def adddivstodoc(thtml):
    """
    put divs around headers
    """
    from lxml import etree, html

    oldbody = html.fromstring('<body>\n' + thtml + '\n</body>')
    newbody = html.fromstring('<html>\n</html>')
    activediv = None
    for child in oldbody.iter():
      if child.getparent() == oldbody:
        if child.tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
          if activediv != None:
            newbody.append(activediv)
            activediv = None

          activediv = etree.fromstring('<div class="indent%s"></div>' \
                                                  % child.tag)
          activediv.append(copy.deepcopy(child))

        elif activediv != None:
          activediv.append(copy.deepcopy(child))
        else:
          newbody.append(copy.deepcopy(child))

    if activediv != None:
      newbody.append(activediv)

    htmlout = etree.tostring(newbody, pretty_print=True)

    html = htmlout.split('\n')

    if html[0] == '<html>':
      html.pop(0)
    while html[-1] == '':
      html.pop()
    lastelem = html.pop()
    lastelem = lastelem.replace('</html>', '')
    if lastelem:
      html.append(lastelem)

    return '\n'.join(html)

  def _build_cmds(self, pmod):
    """
    build the cmds part of the page
    """
    tcmds = self.api('commands.list')(pmod.short_name, cformat=False)

    cmds = []

    if tcmds:
      groups = {}
      for i in sorted(tcmds.keys()):
        if i != 'default':
          if cmds[i]['group'] not in groups:
            groups[cmds[i]['group']] = []

          groups[cmds[i]['group']].append(i)

      cmds = ['<h2 id="commands" class="bph2">Commands</h2>']

      for group in sorted(groups.keys()):
        if group != 'Base':
          cmds.append('<div class="indenth3">')
          cmds.append('<h3 id="cmdgroup%(NAME)s" class="bph3">%(NAME)s</h3>' % \
                        {'NAME':group})
          cmds.append('</div>')
          cmds.append('<div class="indenth4">')
          for i in groups[group]:
            cmds.append('<h4 id="cmd%(NAME)s" class="bph4">%(NAME)s</h4>' % \
                          {'NAME':i})
            cmds.append('<pre><code>')
            chelp = self.api('commands.cmdhelp')(pmod.short_name, i)
            chelp = self.api('colors.colortohtml')(escape(chelp))
            cmds.extend(chelp.split('\n'))
            cmds.append('</code></pre>')
          cmds.append('</div>')

      cmds.append('<div class="indenth3">')
      cmds.append('<h3 id="cmdgroup%(NAME)s" class="bph3">%(NAME)s</h3>' % \
                    {'NAME':'Base'})
      cmds.append('</div>')
      cmds.append('<div class="indenth4">')
      for i in groups['Base']:
        cmds.append('<h4 id="cmd%(NAME)s" class="bph4">%(NAME)s</h4>' % \
                      {'NAME':i})
        cmds.append('<pre><code>')
        chelp = self.api('commands.cmdhelp')(pmod.short_name, i)
        chelp = self.api('colors.colortohtml')(escape(chelp))
        cmds.extend(chelp.split('\n'))
        cmds.append('</code></pre>')
      cmds.append('</div>')

    return cmds

  def _build_settings(self, pmod):
    """
    build the settings for a plugin
    """
    settings = []

    if pmod.settings:
      settings = ['<h2 id="settings" class="bph2">Settings</h2>']
      settings.append('<div class="indenth4">')
      for i in pmod.settings:
        settings.append('<h3 id="set%(NAME)s" class="bph4">%(NAME)s</h3>' % \
                          {'NAME':i})
        settings.append('<pre><code>')
        settings.append('%s' % self.api('colors.colortohtml')(
            escape(pmod.settings[i]['help'])))
        settings.append('</code></pre>')

      settings.append('</div>')

    return settings

  def _build_apis(self, pmod):
    """
    build the api list for the plugin
    """
    papis = self.api('api.getchildren')(pmod.short_name)

    apis = []

    if papis:
      apis = ['<h2 id="api" class="bph2">API</h2>']
      apis.append('<div class="indenth4">')

      for i in papis:
        apis.append('<h3 id="set%(NAME)s" class="bph4">%(NAME)s</h3>' % \
                      {'NAME':i})
        apis.append('<pre><code>')
        tapi = '\n'.join(self.api('api.detail')('%s.%s' % (pmod.short_name, i)))
        tapi = self.api('colors.colortohtml')(escape(tapi))
        apis.extend(tapi.split('\n'))
        apis.append('</code></pre>')

      apis.append('</div>')

    return apis

  def build_plugin(self, plugin, title, pluginmenu, template):
    """
    build a plugin page
    """
    pmod = self.api('plugins.getp')(plugin['plugin_path'])

    if pmod and self.checknodocs(pmod):
      self.api('send.msg')(
          'skipping %s' % plugin['full_import_location'])
      return

    self.api('send.msg')('building %s' % plugin['full_import_location'])

    try:
      testdoc = sys.modules[pmod.full_import_location].__doc__
    except AttributeError:
      self.api('send.msg')('Plugin %s is not loaded' % plugin['plugin_path'])
      return

    wpluginname = '.'.join(plugin['full_import_location'].split('.')[1:])

    body = '<h2 id="about">About</h2>\n' + self.api('colors.colortohtml')(
        markdown2.markdown(testdoc,
                           extras=['header-ids', 'fenced-code-blocks',
                                   'wiki-tables']))

    body = self.adddivstodoc(body)

    body = self.addhclasses(body)

    body = self.addtableclasses(body)

    body.extend(self._build_cmds(pmod))

    body.extend(self._build_settings(pmod))

    body.extend(self._build_apis(pmod))

    testt = self.gettoc('<body>\n' + '\n'.join(body) + '\n</body>')

    ttoc = self.buildtoc(testt)

    html = template % {'BODY':'\n'.join(body), 'TOC':ttoc, 'TITLE':title,
                       'PLUGINMENU':pluginmenu, 'PNAME':wpluginname, 'CSS':'dark.css',
                       'THEMEMENU':self.themelist}

    outdir = os.path.join(self.api.BASEPATH, 'docsout', 'plugins',
                          plugin['full_import_location'].split('.')[1])

    try:
      os.makedirs(outdir)
    except OSError:
      pass

    tfile = open(os.path.join(self.api.BASEPATH,
                              outdir, '%s.html'% pmod.short_name),
                 'w')

    tfile.write(html)

    tfile.close()

  def copy_css(self):
    """
    copy the css files into the output directory
    """
    outpath = os.path.join(self.api.BASEPATH, 'docsout')

    csssrc = os.path.join(self.plugin_directory, 'css')
    cssdst = os.path.join(outpath, 'css')

    dir_util.copy_tree(csssrc, cssdst)

  def copy_favicon(self):
    """
    copy the favicon files into the output directory
    """
    outpath = os.path.join(self.api.BASEPATH, 'docsout')

    favsrc = os.path.join(self.plugin_directory, 'favicon')
    favdst = os.path.join(outpath, 'favicon')

    dir_util.copy_tree(favsrc, favdst)

  def cmd_build(self, _):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    detail a function in the api
      @CUsage@w: detail @Y<api>@w
      @Yapi@w = (optional) the api to detail
    """
    import linecache
    linecache.clearcache()

    if not markdown2:
      if not self.import_markdown2():
        return False

    if not lxml:
      if not self.import_lxml():
        return False

    self.build_themelist()

    temppath = os.path.join(self.plugin_directory, 'templates',
                            'template.html')
    plugininfo = self.api('plugins.allplugininfo')()

    with open(temppath, 'r') as content_file:
      template = content_file.read()

    pmenu = self.buildpluginmenu(plugininfo)

    title = 'Bastproxy'

    self.build_index(title, pmenu, plugininfo, template)

    for i in plugininfo:
      self.build_plugin(plugininfo[i], title, pmenu, template)

    outpath = os.path.join(self.api.BASEPATH, 'docsout')

    self.copy_css()
    self.copy_favicon()

    return True, ['Docs built', 'Directory: %s' % outpath]
