"""
This plugin holds a eq database
"""
import time
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'eqDB'
SNAME = 'eqdb'
PURPOSE = 'Keep track of eq in a database'
AUTHOR = 'Bast'
VERSION = 1



def dbcreate(sqldb, plugin, **kwargs):
  """
  create the eqdb class, this is needed because the Sqldb baseclass
  can be reloaded since it is a plugin
  """
  class EqDb(sqldb):
    """
    a class to manage the eq database
    """
    def __init__(self, plugin, **kwargs):
      """
      initialize the class
      """
      sqldb.__init__(self, plugin, **kwargs)

      self.version = 1

      self.addtable('items', """CREATE TABLE items(
          serial INTEGER NOT NULL,
          keywords TEXT,
          cname TEXT,
          name TEXT,
          level INT default 0,
          itype INT default 0,
          worth INT default 0,
          weight INT default 0,
          wearable TEXT,
          material INT default 0,
          score INT default 0,
          flags TEXT,
          foundat TEXT,
          fromclan TEXT,
          owner TEXT,
          leadsto TEXT,
          UNIQUE(serial),
          PRIMARY KEY(serial)
        );""", keyfield='serial', postcreate=self.additemindexes)

      self.addtable('identifier', """CREATE TABLE identifier(
            serial INTEGER NOT NULL,
            identifier TEXT,
            UNIQUE(identifier),
            PRIMARY KEY(serial, identifier)
          );""")

      self.addtable('resistmod', """CREATE TABLE resistmod(
          rid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          type TEXT,
          amount INT default 0,
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='rid')

      self.addtable('statmod', """CREATE TABLE statmod(
          sid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          type TEXT,
          amount INT default 0,
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='sid')

      self.addtable('affectmod', """CREATE TABLE affectmod(
          aid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          type TEXT,
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='aid')

      self.addtable('skillmod', """CREATE TABLE skillmod(
          skid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          skillnum INT,
          amount INT default 0,
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='skid')

      self.addtable('notes', """CREATE TABLE notes(
          nid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          ntext TEXT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='nid')

      self.addtable('addednotes', """CREATE TABLE addednotes(
          anid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          ntext TEXT
        );""", keyfield='anid')

      self.addtable('weapon', """CREATE TABLE weapon(
          wid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          wtype TEXT,
          damtype TEXT,
          special TEXT,
          inflicts TEXT,
          avedam INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='wid')

      self.addtable('container', """CREATE TABLE container(
          cid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          itemweightpercent INT,
          heaviestitem INT,
          capacity INT,
          holding INT,
          itemsinside INT,
          totalweight INT,
          itemburden INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='cid')

      self.addtable('spells', """CREATE TABLE spells(
          spid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          uses INT,
          level INT,
          sn1 INT,
          sn2 INT,
          sn3 INT,
          sn4 INT,
          u1 INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='spid')

      self.addtable('food', """CREATE TABLE food(
          fid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          percent INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='fid')

      self.addtable('drink', """CREATE TABLE drink(
          did INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          servings INT,
          liquid INT,
          liquidmax INT,
          liquidleft INT,
          thirstpercent INT,
          hungerpercent INT,
          u1 INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='did')

      self.addtable('furniture', """CREATE TABLE furniture(
          fuid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          hpregen INT,
          manaregen INT,
          u1 INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='fuid')

      self.addtable('light', """CREATE TABLE light(
          lid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          duration INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='lid')

      self.addtable('portal', """CREATE TABLE portal(
          portid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          uses INT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='portid')

      self.addtable('enchant', """CREATE TABLE enchant(
          enchantid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          etype TEXT,
          spell TEXT,
          stat TEXT,
          mod INT default 0,
          char text,
          removable text,
          FOREIGN KEY(serial) REFERENCES items(serial)
        );""", keyfield='enchantid')

      self.addtable('reward', """CREATE TABLE reward(
          rewardid INTEGER NOT NULL PRIMARY KEY,
          serial INTEGER NOT NULL,
          rtext TEXT,
          UNIQUE(serial),
          FOREIGN KEY(serial) REFERENCES items(serial)
      );""", keyfield='rewardid')

      # Need to do this after adding tables
      self.postinit()

    def turnonpragmas(self):
      """
      turn on pragmas for eqdb
      """
      self.dbconn.execute("PRAGMA foreign_keys=On;")
      self.dbconn.execute("PRAGMA journal_mode=WAL;")

    def additemindexes(self):
      """
      add item indexes to the database
      """
      pass
      # self.dbconn.execute("""CREATE INDEX IF NOT EXISTS
      #                           xref_items_containerid ON items(containerid);""")
      # self.dbconn.execute("""CREATE INDEX IF NOT EXISTS
      #                           xref_items_name ON items (name);""")
      # self.dbconn.execute("""CREATE INDEX IF NOT EXISTS
      #                           xref_items_level ON items(level);""")
      # self.dbconn.execute("""CREATE INDEX IF NOT EXISTS
      #                           xref_items_place ON items(place);""")

    def countitems(self):
      """
      count the items in the database
      """
      count = -1

      result = self.select("SELECT COUNT(*) as count FROM items")
      if len(result) == 1:
        count = result[0]['count']

      return count

    def getitembyserial(self, serial):
      """
      get an item by serial
      """
      item = None
      serialnum = None
      try:
        serialnum = int(serial)
      except ValueError:
        return None

      select = "SELECT * FROM items WHERE serial = %s;" % serialnum
      self.api('send.msg')('getitembyserial select: "%s"' % select)
      items = self.select(select)
      if len(items) == 1:
        item = items[0]
      else:
        self.api('send.msg')('%s items for serial %s' % (len(items),
                                                         serialnum))

      return item

    def getitembyidentifier(self, identifier):
      """
      get an item by identifier
      """
      item = None
      iditem = None

      select = "SELECT * FROM identifier WHERE identifier = %s;" % \
                                                  self.fixsql(identifier)
      self.api('send.msg')('getitembyidentifier select: "%s"' % select)
      iditems = self.select(select)
      if len(iditems) == 1:
        iditem = iditems[0]
      else:
        self.api('send.msg')('%s items for identifier %s' % (len(iditems),
                                                             identifier))

      if iditem:
        return self.getitembyserial(iditem['serial'])

      return item

    def getitem(self, ident, checkwearslot=False, details=True): # pylint: disable=unused-argument
      """
      get an item from the database
      """
      self.api('send.msg')('eqdb.getitem: %s, details: %s' % (ident, details))
      item = self.getitembyserial(ident)
      if not item:
        item = self.getitembyidentifier(ident)

      if not item:
        item = None
      else:
        if details:
          idetails = self.getitemdetails(item['serial'])
          if details:
            item.update(idetails)

      if item:
        item['flags'] = item['flags'].split(',')
        item['keywords'] = item['keywords'].split(',')

      self.api('send.msg')('eqdb.getitem returned: %s' % item)
      return item

    def getdetail(self, tdet, serial):
      """
      get one detail for an item
      """
      self.api('send.msg')('geting %s for item %s' % (tdet, serial))
      stmt = "SELECT * FROM %s WHERE serial = %s;" % (tdet, serial)
      results = self.api('%s.select' % self.plugin.short_name)(stmt)

      return results

    def getitemdetails(self, serial):
      """
      get all details for an item
      """
      nitem = {}
      statmod = self.getdetail('statmod', serial)
      if statmod:
        newdata = {}
        for i in statmod:
          newdata[i['type']] = i['amount']
        nitem['statmod'] = newdata

      resistmod = self.getdetail('resistmod', serial)
      if resistmod:
        newdata = {}
        for i in resistmod:
          newdata[i['type']] = i['amount']
        nitem['resistmod'] = newdata

      skillmod = self.getdetail('skillmod', serial)
      if skillmod:
        newdata = {}
        for i in skillmod:
          newdata[i['skillnum']] = i['amount']
        nitem['skillmod'] = newdata

      affectmod = self.getdetail('affectmod', serial)
      if affectmod:
        newdata = []
        for i in affectmod:
          newdata.append(i['type'])
        nitem['affectmod'] = newdata

      enchant = self.getdetail('enchant', serial)
      if enchant:
        self.api('send.msg')('enchant returned: %s' % enchant)
        for i in enchant:
          self.api('send.msg')('%s' % i)
          del i['serial']
          del i[self.tables['enchant']['keyfield']]
        nitem['enchant'] = enchant

      for i in ['notes', 'reward', 'weapon', 'light', 'portal',
                'furniture', 'container', 'drink', 'food', 'spells']:
        stuff = self.getdetail(i, serial)
        if stuff:
          stuff = stuff[0]
          del stuff['serial']
          del stuff[self.tables[i]['keyfield']]
          nitem[i] = stuff

      return nitem

    def savemultipledetails(self, tdet, serial, detail):
      """
      save a detail that has many parts, such as stat or resist mods
      details is a dictionary of keys with value
      """
      self.api('send.msg')('adding %s for item %s' % (tdet, serial))
      self.api('send.msg')('detail: %s' % detail)
      self.api('%s.modify' % self.plugin.short_name)('DELETE from %s where serial = %s' % \
                                                  (tdet, serial))
      newdata = []
      for i in detail:
        i['serial'] = serial
        newdata.append(i)

      stmt2 = self.converttoinsert(tdet, keynull=True)
      self.api('send.msg')('sqmt: %s' % stmt2)
      self.api('%s.modifymany' % self.plugin.short_name)(stmt2,
                                                    newdata)

    def saveonedetail(self, tdet, serial, detail):
      """
      save a detail that only has one part, such as weapon
      """
      self.api('send.msg')('adding %s for item %s' % (tdet, serial))
      self.api('send.msg')('detail: %s' % detail)
      self.api('%s.modify' % self.plugin.short_name)('DELETE from %s where serial = %s' % \
                                                  (tdet, serial))
      newitem = self.checkdictforcolumns(tdet, detail)
      newitem['serial'] = serial
      stmt = self.converttoinsert(tdet)
      self.api('%s.modify' % self.plugin.short_name)(stmt, newitem)

    def saveitemdetails(self, item): # pylint: disable=too-many-branches
      """
      save all item details
      """
      if item.checkattr('statmod') and item.statmod:
        data = []
        for mod in item.statmod:
          data.append({'type':mod, 'amount':item.statmod[mod]})
        self.savemultipledetails('statmod', item.serial, data)
      if item.checkattr('resistmod') and item.resistmod:
        data = []
        for mod in item.resistmod:
          data.append({'type':mod, 'amount':item.resistmod[mod]})
        self.savemultipledetails('resistmod', item.serial, data)
      if item.checkattr('skillmod') and item.skillmod:
        data = []
        for mod in item.skillmod:
          data.append({'skillnum':mod, 'amount':item.skillmod[mod]})
        self.savemultipledetails('skillmod', item.serial, data)
      if item.checkattr('affectmod') and item.affectmod:
        data = []
        for mod in item.affectmod:
          data.append({'type':mod})
        self.savemultipledetails('affectmod', item.serial, data)
      if item.checkattr('enchant') and item.enchant:
        self.savemultipledetails('enchant', item.serial, item.enchant)
      if item.checkattr('notes'):
        self.saveonedetail('notes', item.serial, item.notes)
      if item.checkattr('reward'):
        self.saveonedetail('reward', item.serial, item.reward)

      for i in ['weapon', 'light', 'portal', 'furniture', 'container',
                'drink', 'food', 'spells']:
        if item.itype == i.capitalize() and item.checkattr(i):
          self.saveonedetail(i, item.serial, getattr(item, i))

    def saveitem(self, item):
      """
      add an item
      """
      titem = self.getitem(item.serial, details=False)
      self.api('send.msg')('saveitem: %s' % item)
      if not titem:
        self.api('send.msg')('adding item: %s' % item.serial)
        newitem = self.checkdictforcolumns('items', vars(item))
        newitem['keywords'] = ",".join(newitem['keywords'])
        newitem['flags'] = ",".join(newitem['flags'])
        stmt = self.converttoinsert('items')
        self.api('%s.modify' % self.plugin.short_name)(stmt, newitem)
      else:
        self.api('send.msg')('updating item: %s' % item.serial)
        newitem = self.checkdictforcolumns('items', vars(item))
        newitem['keywords'] = ",".join(newitem['keywords'])
        newitem['flags'] = ",".join(newitem['flags'])
        stmt = self.converttoupdate('items', 'serial')
        self.api('%s.modify' % self.plugin.short_name)(stmt, newitem)

      self.saveitemdetails(item)

  return EqDb(plugin, **kwargs)

class Plugin(AardwolfBasePlugin):
  """
  a plugin to monitor aardwolf events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.eqdb = None

    self.api('dependency.add')('core.sqldb')
    self.api('api.add')('getitem', self.api_loaditem)
    self.api('api.add')('saveitem', self.api_saveitem)

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.eqdb = dbcreate(self.api('sqldb.baseclass')(), self,
                         dbname='eqdb', dbdir=self.save_directory)

    self.api('setting.add')('backupstart', '0000', 'miltime',
                            'the time for a db backup, like 1200 or 2000')
    self.api('setting.add')('backupinterval', 60*60*4, int,
                            'the interval to backup the db, default every 4 hours')

    parser = argp.ArgumentParser(add_help=False,
                                 description='get item')
    parser.add_argument('id', help='the identifier/serial/wearloc',
                        default='', nargs='?')
    self.api('commands.add')('getitem', self.cmd_getitem,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='test')
    self.api('commands.add')('test', self.cmd_test,
                             parser=parser)

    #self.api('events.register')('GMCP:char.status', self.checkstats)
    self.api('events.register')('statdb_backupstart', self.changetimer)
    self.api('events.register')('statdb_backupinternval', self.changetimer)

    self.api('events.register')('trigger_dead', self.dead)

    self.api('timers.add')('eq_backup', self.backupdb,
                           self.api('setting.gets')('backupinterval'),
                           time=self.api('setting.gets')('backupstart'))

  def changetimer(self, _=None):
    """
    do something when the reportminutes changes
    """
    backupinterval = self.api('setting.gets')('backupinterval')
    backupstart = self.api('setting.gets')('backupstart')
    self.api('timers.remove')('eq_backup')
    self.api('timers.add')('eq_backup', self.backupdb,
                           backupinterval, time=backupstart)

  def backupdb(self):
    """
    backup the db from the timer
    """
    tstr = time.strftime('%a-%b-%d-%Y-%H-%M', time.localtime())
    if self.eqdb:
      self.eqdb.backupdb(tstr)

  def dead(self, _):
    """
    add to timeskilled when dead
    """
    pass
    #self.statdb.addtostat('timeskilled', 1)

  def api_loaditem(self, serial):
    """
    get an item from the database
    """
    return self.eqdb.getitem(serial)

  def api_saveitem(self, item):
    """
    save an item to the database
    """
    self.eqdb.saveitem(item)

  def cmd_getitem(self, args=None):
    """
    show quest stats
    """
    identifier = None
    if args and args['id']:
      identifier = args['id']

    if not identifier:
      return True, ['Please enter an serial/identifier/wearloc to show']

    item = self.eqdb.getitem(identifier, True)

    if not item:
      return True, ['There is no item with that serial/identifier/wearloc']

    return True, ['Item: %s' % item]

  def cmd_test(self, _=None):
    """
    test command
    """
    tmsg = []
    select = """select * from items
            left join weapon on items.serial = weapon.serial
            left join light on items.serial = light.serial
            left join container on items.serial = container.serial
            left join portal on items.serial = portal.serial
            where items.serial = 424276787;"""

    tmsg.append('select: %s' % select)
    stuff = self.eqdb.select(select)

    tmsg.append('result: %s' % stuff)
    tmsg.append('')
    select = """select * from items
            left outer join weapon on items.serial = weapon.serial
            left outer join light on items.serial = light.serial
            left outer join container on items.serial = container.serial
            left outer join portal on items.serial = portal.serial
            where items.serial = 424276787;"""

    tmsg.append('select: %s' % select)
    stuff = self.eqdb.select(select)

    tmsg.append('result: %s' % stuff)

    tmsg.append('')
    select = """select * from items
            join weapon on items.serial = weapon.serial
            join light on items.serial = light.serial
            join container on items.serial = container.serial
            join portal on items.serial = portal.serial
            where items.serial = 424276787;"""

    tmsg.append('select: %s' % select)
    stuff = self.eqdb.select(select)

    tmsg.append('result: %s' % stuff)

    return True, tmsg

  def uninitialize(self, _=None):
    """
    handle uninitializing
    """
    AardwolfBasePlugin.uninitialize(self)
    self.eqdb.close()
