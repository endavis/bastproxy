# pylint: disable=too-many-lines
"""
This plugin holds a stat database and collects the following:

 * levels
 * pups
 * quests
 * cp
 * gqs
 * mobkills

"""
import copy
import time
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'StatDB'
SNAME = 'statdb'
PURPOSE = 'Add events to the stat database'
AUTHOR = 'Bast'
VERSION = 2



def format_float(item, addto=""):
  """
  format a floating point #
  """
  if item:
    tempt = "%.03f%s" % (item, addto)
  else:
    tempt = 0
  return tempt

FIELDSTOCOMP = ['totallevels',
                'qpearned',
                'questscomplete',
                'questsfailed',
                'campaignsdone',
                'campaignsfld',
                'gquestswon',
                'duelswon',
                'duelslost',
                'timeskilled',
                'monsterskilled',
                'combatmazewins',
                'combatmazedeaths',
                'powerupsall',
                'totaltrivia']

def dbcreate(sqldb, plugin, **kwargs):
  """
  create the statdb class, this is needed because the Sqldb baseclass
  can be reloaded since it is a plugin
  """
  class Statdb(sqldb): # pylint: disable=too-many-public-methods
    """
    a class to manage a sqlite database for aardwolf events
    """
    def __init__(self, plugin, **kwargs):
      """
      initialize the class
      """
      sqldb.__init__(self, plugin, **kwargs)

      self.version = 17

      self.version_functions[13] = self.addrarexp_v13
      self.version_functions[14] = self.addnoexp_v14
      self.version_functions[15] = self.addextendedgq_v15
      self.version_functions[16] = self.addhardcoreopk_v16
      self.version_functions[17] = self.addlevelbattlelearntrains_v17

      self.addtable('stats', """CREATE TABLE stats(
            stat_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            name TEXT NOT NULL,
            level INT default 1,
            totallevels INT default 1,
            remorts INT default 1,
            tiers INT default 0,
            race TEXT default "",
            sex TEXT default "",
            subclass TEXT default "",
            qpearned INT default 0,
            questscomplete INT default 0 ,
            questsfailed INT default 0,
            campaignsdone INT default 0,
            campaignsfld INT default 0,
            gquestswon INT default 0,
            duelswon INT default 0,
            duelslost INT default 0,
            timeskilled INT default 0,
            monsterskilled INT default 0,
            combatmazewins INT default 0,
            combatmazedeaths INT default 0,
            powerupsall INT default 0,
            totaltrivia INT default 0,
            time INT default 0,
            milestone TEXT,
            redos INT default 0
          );""", keyfield='stat_id')

#
      self.addtable('quests', """CREATE TABLE quests(
            quest_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            starttime INT default 0,
            finishtime INT default 0,
            mobname TEXT default "Unknown",
            mobarea TEXT default "Unknown",
            mobroom TEXT default "Unknown",
            qp INT default 0,
            double INT default 0,
            daily INT default 0,
            totqp INT default 0,
            gold INT default 0,
            tierqp INT default 0,
            mccp INT default 0,
            lucky INT default 0,
            opk INT default 0,
            hardcore INT default 0,
            tp INT default 0,
            trains INT default 0,
            pracs INT default 0,
            level INT default -1,
            failed INT default 0
          );""", keyfield='quest_id')

      self.addtable('classes', """CREATE TABLE classes(
              class TEXT NOT NULL PRIMARY KEY,
              remort INTEGER
            );""", keyfield='class', postcreate=self.initclasses)

      self.addtable('levels', """CREATE TABLE levels(
            level_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            type TEXT default "level",
            level INT default -1,
            str INT default 0,
            int INT default 0,
            wis INT default 0,
            dex INT default 0,
            con INT default 0,
            luc INT default 0,
            starttime INT default -1,
            finishtime INT default -1,
            hp INT default 0,
            mp INT default 0,
            mv INT default 0,
            pracs INT default 0,
            trains INT default 0,
            bonustrains INT default 0,
            blessingtrains INT default 0,
            battlelearntrains INT default 0
          )""", keyfield='level_id')

      self.addtable('campaigns', """CREATE TABLE campaigns(
            cp_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            starttime INT default 0,
            finishtime INT default 0,
            qp INT default 0,
            bonusqp INT default 0,
            gold INT default 0,
            tp INT default 0,
            trains INT default 0,
            pracs INT default 0,
            level INT default -1,
            failed INT default 0
          );""", keyfield='cp_id')

      self.addtable('cpmobs', """CREATE TABLE cpmobs(
            cpmob_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            cp_id INT NOT NULL,
            name TEXT default "Unknown",
            location TEXT default "Unknown"
          )""", keyfield='cpmob_id')

      self.addtable('mobkills', """CREATE TABLE mobkills(
            mk_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            name TEXT default "Unknown",
            xp INT default 0,
            rarexp INT default 0,
            bonusxp INT default 0,
            blessingxp INT default 0,
            totalxp INT default 0,
            noexp INT default 0,
            gold INT default 0,
            tp INT default 0,
            time INT default -1,
            vorpal INT default 0,
            banishment INT default 0,
            assassinate INT default 0,
            slit INT default 0,
            disintegrate INT default 0,
            deathblow INT default 0,
            wielded_weapon TEXT default '',
            second_weapon TEXT default '',
            room_id INT default 0,
            level INT default -1
          )""", keyfield='mk_id')

      self.addtable('gquests', """CREATE TABLE gquests(
            gq_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            starttime INT default 0,
            finishtime INT default 0,
            qp INT default 0,
            qpmobs INT default 0,
            gold INT default 0,
            tp INT default 0,
            trains INT default 0,
            pracs INT default 0,
            level INT default -1,
            extended INT default 0,
            won INT default 0,
            completed INT default 0
          )""", keyfield='gq_id')


      self.addtable('gqmobs', """CREATE TABLE gqmobs(
            gqmob_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            gq_id INT NOT NULL,
            num INT,
            name TEXT default "Unknown",
            location TEXT default "Unknown"
          )""", keyfield='gqmob_id')

      # Need to do this after adding tables
      self.postinit()

    def turnonpragmas(self):
      """
      turn on pragmas for the database
      """
      #-- PRAGMA foreign_keys = ON;
      self.dbconn.execute("PRAGMA foreign_keys=On;")
      #-- PRAGMA journal_mode=WAL
      self.dbconn.execute("PRAGMA journal_mode=WAL;")

    def savequest(self, questinfo):
      """
      save a quest in the db
      """
      if questinfo['failed'] == 1:
        self.addtostat('questsfailed', 1)
      else:
        self.addtostat('questscomplete', 1)
        self.addtostat('questpoints', questinfo['totqp'])
        self.addtostat('qpearned', questinfo['totqp'])
        self.addtostat('triviapoints', questinfo['tp'])
        self.addtostat('totaltrivia', questinfo['tp'])

      questinfo = self.checkdictforcolumns('quests', questinfo)

      stmt = self.converttoinsert('quests', keynull=True)
      rowid, _ = self.api('%s:modify' % (self.database_name))(stmt, questinfo)
      self.api('libs.io:send:msg')('added quest: %s' % rowid)
      return rowid

    def remove(self, table, rownumber):
      """
      remove an item
      """
      retval, msg = sqldb.remove(self, table, rownumber)

      if retval:
        if table == 'campaigns':
          stmt = "DELETE FROM cpmobs where cp_id=%s;" % (rownumber)
          self.api('%s:modify' % (self.database_name))(stmt)

        elif table == 'gquests':
          stmt = "DELETE FROM gqmobs where gq_id=%s;" % (rownumber)
          self.api('%s:modify' % (self.database_name))(stmt)

      return retval, msg

    def setstat(self, stat, value):
      """
      set a stat
      """
      stmt = 'update stats set %s=%s where milestone = "current"' % (
          stat, value)
      self.api('%s:modify' % (self.database_name))(stmt)
      self.api('libs.io:send:msg')('set %s to %s' % (stat, value))

    def getstat(self, stat):
      """
      get a stat from the stats table
      """
      tstat = None
      rows = self.api('%s:select' % (self.database_name))(
          'SELECT * FROM stats WHERE milestone = "current"')
      if len(rows) > 0 and stat in rows[0]: # pylint: disable=len-as-condition
        tstat = rows[0][stat]
      return tstat

    def addtostat(self, stat, add):
      """
      add to  a stat in the stats table
      """
      if add <= 0:
        return True

      if self.checkcolumnexists('stats', stat):
        stmt = "UPDATE stats SET %s = %s + %s WHERE milestone = 'current'" \
            % (stat, stat, add)
        self.api('%s:modify' % (self.database_name))(stmt)
        return True

      return False

    def savewhois(self, whoisinfo):
      """
      save info into the stats table
      """
      if self.getstat('totallevels'):
        nokey = {}
        nokey['stat_id'] = True
        nokey['totaltrivia'] = True
        whoisinfo['milestone'] = 'current'
        whoisinfo['time'] = 0
        stmt = self.converttoupdate('stats', 'milestone', nokey)
        self.api('%s:modify' % (self.database_name))(stmt, whoisinfo)
      else:
        whoisinfo['milestone'] = 'current'
        whoisinfo['totaltrivia'] = 0
        whoisinfo['time'] = 0
        stmt = self.converttoinsert('stats', True)
        self.api('%s:modify' % (self.database_name))(stmt, whoisinfo)
        #add a milestone here
        self.addmilestone('start')

      self.api('libs.io:send:msg')('updated stats')
      # add classes here
      self.addclasses(whoisinfo['classes'])

    def addmilestone(self, milestone):
      """
      add a milestone
      """
      if not milestone:
        return -1

      trows = self.api('%s:select' % (self.database_name))(
          'SELECT * FROM stats WHERE milestone = "%s"' \
                                                            % milestone)
      if len(trows) > 0: # pylint: disable=len-as-condition
        self.api('libs.io:send:client')('@RMilestone %s already exists' % \
                                                milestone)
        return -1

      stats = self.api('%s:select' % (self.database_name))(
          'SELECT * FROM stats WHERE milestone = "current"')
      tstats = stats[0]

      if tstats:
        tstats['milestone'] = milestone
        tstats['time'] = time.time()
        stmt = self.converttoinsert('stats', True)
        rowid, _ = self.api('%s:modify' % (self.database_name))(stmt, tstats)

        self.api('libs.io:send:msg')('inserted milestone %s with rowid: %s' % (
            milestone, rowid))
        return rowid

      return -1

    def getmilestone(self, milestone):
      """
      get a milestone
      """
      trows = self.api('%s:select' % (self.database_name))(
          'SELECT * FROM stats WHERE milestone = "%s"' % milestone)

      if len(trows) == 0: # pylint: disable=len-as-condition
        return None

      return trows[0]

    def addclasses(self, classes):
      """
      add classes from whois
      """
      stmt = 'UPDATE CLASSES SET REMORT = :remort WHERE class = :class'
      self.api('%s:modify:many' % (self.database_name))(stmt, classes)

    def getclasses(self):
      """
      get all classes
      """
      classes = []
      tclasses = self.api('%s:select' % (self.database_name))(
          'SELECT * FROM classes ORDER by remort ASC')
      for i in tclasses:
        if i['remort'] != -1:
          classes.append(i['class'])

      return classes

    def initclasses(self):
      """
      initialize the class table
      """
      classabb = self.api('aardwolf.aardu:classabb')()
      classes = []
      for i in classabb:
        classes.append({'class':i})
      stmt = "INSERT INTO classes VALUES (:class, -1)"
      self.api('%s:%s:modify:many' % (self.plugin.plugin_id, self.database_name))(stmt,
                                                                                  classes)

    def resetclasses(self):
      """
      reset the class table
      """
      classabb = self.api('aardu.classabb')()
      classes = []
      for i in classabb:
        classes.append({'class':i})
      stmt = """UPDATE classes SET remort = -1
                      WHERE class = :class"""
      self.api('%s:modify:many' % (self.database_name))(stmt, classes)

    def savecp(self, cpinfo):
      """
      save cp information
      """
      if cpinfo['failed'] == 1:
        self.addtostat('campaignsfld', 1)
      else:
        self.addtostat('campaignsdone', 1)
        self.addtostat('questpoints', cpinfo['qp'])
        self.addtostat('qpearned', cpinfo['qp'])
        self.addtostat('triviapoints', cpinfo['tp'])
        self.addtostat('totaltrivia', cpinfo['tp'])

      cpinfo = self.checkdictforcolumns('campaigns', cpinfo)

      stmt = self.converttoinsert('campaigns', keynull=True)
      rowid, _ = self.api('%s:modify' % (self.database_name))(stmt, cpinfo)
      self.api('libs.io:send:msg')('added cp: %s' % rowid)

      for i in cpinfo['mobs']:
        i['cp_id'] = rowid
      stmt2 = self.converttoinsert('cpmobs', keynull=True)
      self.api('modify:many' % (self.database_name))(stmt2, cpinfo['mobs'])

    def savegq(self, gqinfo):
      """
      save gq information
      """
      self.addtostat('questpoints', int(gqinfo['qp']) + int(gqinfo['qpmobs']))
      self.addtostat('qpearned', int(gqinfo['qp']) + int(gqinfo['qpmobs']))
      self.addtostat('triviapoints', gqinfo['tp'])
      self.addtostat('totaltrivia', gqinfo['tp'])
      if gqinfo['won'] == 1:
        self.addtostat('gquestswon', 1)

      gqinfo = self.checkdictforcolumns('gquests', gqinfo)

      stmt = self.converttoinsert('gquests', keynull=True)
      rowid, _ = self.api('%s:modify' % (self.database_name))(stmt, gqinfo)
      self.api('libs.io:send:msg')('added gq: %s' % rowid)

      for i in gqinfo['mobs']:
        i['gq_id'] = rowid
      stmt2 = self.converttoinsert('gqmobs', keynull=True)
      self.api('%s:modify:many' % (self.database_name))(stmt2, gqinfo['mobs'])

    def savelevel(self, levelinfo, first=False):
      """
      save a level
      """
      rowid = -1
      if not first:
        if levelinfo['type'] == 'level':
          if levelinfo['totallevels'] and levelinfo['totallevels'] > 0:
            self.setstat('totallevels', levelinfo['totallevels'])
            self.setstat('level', levelinfo['level'])
          else:
            self.addtostat('totallevels', 1)
            self.addtostat('level', 1)
        elif levelinfo['type'] == 'pup':
          self.addtostat('powerupsall', 1)
        if levelinfo['totallevels'] and levelinfo['totallevels'] > 0:
          levelinfo['level'] = levelinfo['totallevels']
        else:
          levelinfo['level'] = self.getstat('totallevels')

      levelinfo['finishtime'] = -1

      levelinfo = self.checkdictforcolumns('levels', levelinfo)

      stmt = self.converttoinsert('levels', keynull=True)
      rowid, _ = self.api('%s:modify' % (self.database_name))(stmt, levelinfo)
      self.api('libs.io:send:msg')('inserted level %s' % rowid)
      if rowid > 1:
        stmt2 = "UPDATE levels SET finishtime = %s WHERE level_id = %d" % (
            levelinfo['starttime'], int(rowid) - 1)
        self.api('%s:modify' % (self.database_name))(stmt2)

      if levelinfo['type'] == 'level':
        self.addmilestone(str(levelinfo['totallevels']))

      return rowid

    def savemobkill(self, killinfo):
      """
      save a mob kill
      """
      self.addtostat('totaltrivia', killinfo['tp'])
      self.addtostat('monsterskilled', 1)

      killinfo = self.checkdictforcolumns('mobkills', killinfo)

      stmt = self.converttoinsert('mobkills', keynull=True)
      rowid, _ = self.api('%s:modify' % (self.database_name))(stmt, killinfo)
      self.api('libs.io:send:msg')('inserted mobkill: %s' % rowid)

    def addrarexp_v13(self):
      """
      add rare xp into the database
      """
      if not self.checktableexists('mobkills'):
        return

      oldmobst = self.select('SELECT * FROM mobkills ORDER BY mk_id ASC')

      cur = self.dbconn.cursor()
      cur.execute('DROP TABLE IF EXISTS mobkills;')
      cur.close()
      self.close()

      self.open()
      cur = self.dbconn.cursor()
      cur.execute("""CREATE TABLE mobkills(
            mk_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            name TEXT default "Unknown",
            xp INT default 0,
            rarexp INT default 0,
            bonusxp INT default 0,
            blessingxp INT default 0,
            totalxp INT default 0,
            gold INT default 0,
            tp INT default 0,
            time INT default -1,
            vorpal INT default 0,
            banishment INT default 0,
            assassinate INT default 0,
            slit INT default 0,
            disintegrate INT default 0,
            deathblow INT default 0,
            wielded_weapon TEXT default '',
            second_weapon TEXT default '',
            room_id INT default 0,
            level INT default -1
          )""")
      cur.close()

      cur = self.dbconn.cursor()
      stmt2 = """INSERT INTO mobkills VALUES (:mk_id, :name, :xp, 0,
                    :bonusxp, :blessingxp, :totalxp, :gold, :tp, :time,
                    :vorpal, :banishment, :assassinate, :slit, :disintegrate,
                    :deathblow, :wielded_weapon, :second_weapon, :room_id,
                    :level)"""
      cur.executemany(stmt2, oldmobst)
      cur.close()

    def addnoexp_v14(self):
      """
      add noexp to each mobkill
      """
      if not self.checktableexists('mobkills'):
        return

      oldmobst = self.select('SELECT * FROM mobkills ORDER BY mk_id ASC')

      cur = self.dbconn.cursor()
      cur.execute('DROP TABLE IF EXISTS mobkills;')
      cur.close()
      self.close()

      self.open()
      cur = self.dbconn.cursor()

      cur.execute("""CREATE TABLE mobkills(
            mk_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            name TEXT default "Unknown",
            xp INT default 0,
            rarexp INT default 0,
            bonusxp INT default 0,
            blessingxp INT default 0,
            totalxp INT default 0,
            noexp INT default 0,
            gold INT default 0,
            tp INT default 0,
            time INT default -1,
            vorpal INT default 0,
            banishment INT default 0,
            assassinate INT default 0,
            slit INT default 0,
            disintegrate INT default 0,
            deathblow INT default 0,
            wielded_weapon TEXT default '',
            second_weapon TEXT default '',
            room_id INT default 0,
            level INT default -1
          )""")
      cur.close()

      cur = self.dbconn.cursor()
      stmt2 = """INSERT INTO mobkills VALUES (:mk_id, :name, :xp, 0,
                    :bonusxp, :blessingxp, :totalxp, 0, :gold, :tp, :time,
                    :vorpal, :banishment, :assassinate, :slit, :disintegrate,
                    :deathblow, :wielded_weapon, :second_weapon, :room_id,
                    :level)"""
      cur.executemany(stmt2, oldmobst)
      cur.close()

    def addextendedgq_v15(self):
      """
      add noexp to each mobkill
      """
      if not self.checktableexists('gquests'):
        return

      oldgqt = self.select('SELECT * FROM gquests ORDER BY gq_id ASC')

      cur = self.dbconn.cursor()
      cur.execute('DROP TABLE IF EXISTS gquests;')
      cur.close()
      self.close()

      self.open()
      cur = self.dbconn.cursor()

      cur.execute("""CREATE TABLE gquests(
            gq_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            starttime INT default 0,
            finishtime INT default 0,
            qp INT default 0,
            qpmobs INT default 0,
            gold INT default 0,
            tp INT default 0,
            trains INT default 0,
            pracs INT default 0,
            level INT default -1,
            extended INT default 0,
            won INT default 0,
            completed INT default 0
          )""")
      cur.close()

      for gqd in oldgqt:
        if gqd['completed'] == 1:
          gqd['extended'] = 1
        else:
          gqd['extended'] = 0

      cur = self.dbconn.cursor()
      stmt2 = """INSERT INTO gquests VALUES (:gq_id, :starttime, :finishtime,
                    :qp, :qpmobs, :gold, :tp, :trains, :pracs, :level,
                    :extended, :won, :completed)"""
      cur.executemany(stmt2, oldgqt)
      cur.close()

    def addhardcoreopk_v16(self):
      """
      add noexp to each mobkill
      """
      if not self.checktableexists('quests'):
        return

      olditems = self.select('SELECT * FROM quests ORDER BY quest_id ASC')

      cur = self.dbconn.cursor()
      cur.execute('DROP TABLE IF EXISTS quests;')
      cur.close()
      self.close()

      self.open()
      cur = self.dbconn.cursor()

      cur.execute("""CREATE TABLE quests(
            quest_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            starttime INT default 0,
            finishtime INT default 0,
            mobname TEXT default "Unknown",
            mobarea TEXT default "Unknown",
            mobroom TEXT default "Unknown",
            qp INT default 0,
            double INT default 0,
            daily INT default 0,
            totqp INT default 0,
            gold INT default 0,
            tierqp INT default 0,
            mccp INT default 0,
            lucky INT default 0,
            opk INT default 0,
            hardcore INT default 0,
            tp INT default 0,
            trains INT default 0,
            pracs INT default 0,
            level INT default -1,
            failed INT default 0
          );""")
      cur.close()

      for item in olditems:
        item['tierqp'] = item['tier']
        item['opk'] = 0
        item['hardcore'] = 0

      cur = self.dbconn.cursor()
      stmt2 = """INSERT INTO quests VALUES (:quest_id, :starttime, :finishtime,
                    :mobname, :mobarea, :mobroom, :qp, :double, :daily, :totqp,
                    :gold, :tierqp, :mccp, :lucky, :opk, :hardcore, :tp,
                    :trains, :pracs, :level, :failed)"""
      cur.executemany(stmt2, olditems)
      cur.close()

    def addlevelbattlelearntrains_v17(self):
      """
      add battle learning trains to the level table
      """
      if not self.checktableexists('levels'):
        return

      olditems = self.select('SELECT * FROM levels ORDER BY level_id ASC')

      cur = self.dbconn.cursor()
      cur.execute('DROP TABLE IF EXISTS levels;')
      cur.close()
      self.close()

      self.open()
      cur = self.dbconn.cursor()

      cur.execute("""CREATE TABLE levels(
            level_id INTEGER NOT NULL PRIMARY KEY autoincrement,
            type TEXT default "level",
            level INT default -1,
            str INT default 0,
            int INT default 0,
            wis INT default 0,
            dex INT default 0,
            con INT default 0,
            luc INT default 0,
            starttime INT default -1,
            finishtime INT default -1,
            hp INT default 0,
            mp INT default 0,
            mv INT default 0,
            pracs INT default 0,
            trains INT default 0,
            bonustrains INT default 0,
            blessingtrains INT default 0,
            battlelearntrains INT default 0
          )""")

      cur.close()

      for item in olditems:
        item['battlelearntrains'] = 0

      cur = self.dbconn.cursor()
      stmt2 = """INSERT INTO levels VALUES (:level_id, :type, :level,
                    :str, :int, :wis, :dex, :con, :luc,
                    :starttime, :finishtime, :hp, :mp, :mv, :pracs,
                    :trains, :bonustrains, :blessingtrains, :battlelearntrains)"""
      cur.executemany(stmt2, olditems)
      cur.close()

  return Statdb(plugin, **kwargs)


class Plugin(AardwolfBasePlugin): # pylint: disable=too-many-public-methods
  """
  a plugin to catch aardwolf stats and add them to a database
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency:add')('core.sqldb')
    self.api('dependency:add')('core.timers')
    self.api('dependency:add')('aardwolf.whois')
    self.api('dependency:add')('aardwolf.level')
    self.api('dependency:add')('aardwolf.mobk')
    self.api('dependency:add')('aardwolf.cp')
    self.api('dependency:add')('aardwolf.gq')
    self.api('dependency:add')('aardwolf.quest')

    self.database_name = 'stats'
    self.statdb = None

    self.version_functions[2] = self.movestatdb_version2

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.statdb = dbcreate(self.api('core.sqldb:baseclass')(), self,
                           dbname=self.database_name, dbdir=self.save_directory)

    self.api('setting:add')('backupstart', '0000', 'miltime',
                            'the time for a db backup, ex. 1200 or 2000')
    self.api('setting:add')('backupinterval', '4h', 'timelength',
                            'the interval to backup the db, default every 4 hours')

    parser = argp.ArgumentParser(add_help=False,
                                 description='list milestones')
    self.api('core.commands:command:add')('list', self.cmd_list,
                                          parser=parser, group='Milestones')

    parser = argp.ArgumentParser(add_help=False,
                                 description='compare milestones')
    parser.add_argument('milestone1', help='the first milestone',
                        default='', nargs='?')
    parser.add_argument('milestone2', help='the second milestone',
                        default='', nargs='?')
    self.api('core.commands:command:add')('comp', self.cmd_comp,
                                          parser=parser, group='Milestones')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show quests stats')
    parser.add_argument('count', help='the number of quests to show',
                        default=0, nargs='?')
    parser.add_argument('-n', "--number",
                        help="show info for level number",
                        default='')
    self.api('core.commands:command:add')('quests', self.cmd_quests,
                                          parser=parser, group='Stats')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show level stats')
    parser.add_argument('count', help='the number of levels to show',
                        default=0, nargs='?')
    parser.add_argument('-n', "--number",
                        help="show info for level number",
                        default='')
    self.api('core.commands:command:add')('levels', self.cmd_levels,
                                          parser=parser, group='Stats')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show cp stats')
    parser.add_argument('count', help='the number of cps to show',
                        default=0, nargs='?')
    parser.add_argument('-n', "--number",
                        help="show info for cp number",
                        default='')
    self.api('core.commands:command:add')('cps', self.cmd_cps,
                                          parser=parser, group='Stats')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show gq stats')
    parser.add_argument('count', help='the number of gqs to show',
                        default=0, nargs='?')
    parser.add_argument('-n', "--number",
                        help="show info for gq number",
                        default='')
    self.api('core.commands:command:add')('gqs', self.cmd_gqs,
                                          parser=parser, group='Stats')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show mob stats')
    parser.add_argument('count', help='the number of mobkills to show',
                        default=0, nargs='?')
    self.api('core.commands:command:add')('mobs', self.cmd_mobs,
                                          parser=parser, group='Stats')

    self.api('core.events:register:to:event')('aard_quest_comp', self.questevent)
    self.api('core.events:register:to:event')('aard_quest_failed', self.questevent)
    self.api('core.events:register:to:event')('aard_cp_comp', self.cpevent)
    self.api('core.events:register:to:event')('aard_cp_failed', self.cpevent)
    self.api('core.events:register:to:event')('aard_whois', self.whoisevent)
    self.api('core.events:register:to:event')('aard_level_gain', self.levelevent)
    self.api('core.events:register:to:event')('aard_level_hero', self.heroevent)
    self.api('core.events:register:to:event')('aard_level_superhero', self.heroevent)
    self.api('core.events:register:to:event')('aard_level_remort', self.heroevent)
    self.api('core.events:register:to:event')('aard_level_tier', self.heroevent)
    self.api('core.events:register:to:event')('aard_mobkill', self.mobkillevent)
    self.api('core.events:register:to:event')('aard_gq_completed', self.gqevent)
    self.api('core.events:register:to:event')('aard_gq_done', self.gqevent)
    self.api('core.events:register:to:event')('aard_gq_won', self.gqevent)
    self.api('core.events:register:to:event')('GMCP:char.status', self.checkstats)
    self.api('core.events:register:to:event')('%s_var_backupstart_modified' % self.plugin_id, self.changetimer)
    self.api('core.events:register:to:event')('%s_var_backupinternval_modified' % self.plugin_id,
                                              self.changetimer)

    self.api('core.events:register:to:event')('trigger_dead', self.dead)

    self.api('core.timers:add:timer')('stats_backup', self.backupdb,
                                      self.api('setting:get')('backupinterval'),
                                      time=self.api('setting:get')('backupstart'))

  def movestatdb_version2(self):
    """
    upgrade to version 2
    """
    import os
    import glob
    import shutil

    oldpath = os.path.join(self.api.BASEPATH, 'data', 'db')
    oldpatharchive = os.path.join(oldpath, 'archive')
    newpath = self.save_directory
    newpatharchive = os.path.join(newpath, 'archive')
    if not os.path.exists(newpatharchive):
      os.makedirs(newpatharchive)

    for filename in glob.glob(os.path.join(oldpath, 'stats*')):
      shutil.move(filename, newpath)

    for filename in glob.glob(os.path.join(oldpatharchive, 'stats*')):
      shutil.move(filename, newpatharchive)


  def changetimer(self, _=None):
    """
    do something when the reportminutes changes
    """
    backupinterval = self.api('setting:get')('backupinterval')
    backupstart = self.api('setting:get')('backupstart')
    self.api('core.timers:remove:timer')('stats_backup')
    self.api('core.timers:add:timer')('stats_backup', self.backupdb,
                                      backupinterval, time=backupstart)

  def backupdb(self):
    """
    backup the db from the timer
    """
    tstr = time.strftime('%a-%b-%d-%Y-%H-%M', time.localtime())
    if self.statdb:
      self.statdb.backupdb(tstr)

  def dead(self, _):
    """
    add to timeskilled when dead
    """
    self.statdb.addtostat('timeskilled', 1)

  def checkstats(self, _=None):
    """
    check to see if we have stats
    """
    state = self.api('net.GMCP:value:get')('char.status.state')
    if state == 3:
      self.api('core.events:unregister:from:event')('GMCP:char.status', self.checkstats)
      if not self.statdb.getstat('monsterskilled'):
        self.api('libs.io:send:execute')('whois')

  def cmd_list(self, _=None):
    """
    list milestones
    """
    msg = []
    milest = self.statdb.select('SELECT milestone FROM stats')
    levels = self.statdb.select(
        "SELECT MIN(totallevels) as MIN, MAX(totallevels) as MAX FROM stats " \
                "WHERE stats.totallevels == stats.milestone")

    maxlev = 0
    minlev = 0
    for row in levels:
      maxlev = row['MAX']
      minlev = row['MIN']

    if maxlev and minlev:
      msg.append('Levels between %s and %s' % (minlev, maxlev))

    items = []
    for row in milest:
      try:
        int(row['milestone'])
      except ValueError:
        items.append(row['milestone'])
      if len(items) == 3:
        msg.append('%-15s %-15s %-15s' % (items[0], items[1], items[2]))
        items = []

    if len(items) > 0: # pylint: disable=len-as-condition
      if len(items) == 1:
        msg.append('%-15s' % items[0])
      elif len(items) == 2:
        msg.append('%-15s %-15s' % (items[0], items[1]))

    if not msg:
      msg.append('No milestones')

    return True, msg

  def formatcomp(self, milestone1, milestone2):
    """
    format a milestone comparison
    """
    msg = []

    tformat = "%-17s %-15s %-15s %-10s"
    msg.append(tformat % ('Milestone', milestone1['milestone'],
                          milestone2['milestone'], 'Difference'))

    msg.append('@g' + '-' * 60)

    if milestone1['time'] == 0:
      milestone1['dates'] = 'Now'
      milestone1['times'] = ''
      milestone1['time'] = time.time()
    else:
      milestone1['dates'] = time.strftime('%x',
                                          time.localtime(milestone1['time']))
      milestone1['times'] = time.strftime('%X',
                                          time.localtime(milestone1['time']))

    if milestone2['time'] == 0:
      milestone2['dates'] = 'Now'
      milestone2['times'] = ''
      milestone2['time'] = time.time()
    else:
      milestone2['dates'] = time.strftime('%x',
                                          time.localtime(milestone2['time']))
      milestone2['times'] = time.strftime('%X',
                                          time.localtime(milestone2['time']))

    if milestone2['time'] < milestone1['time']:
      tmp1 = milestone1
      tmp2 = milestone2

      milestone1 = tmp2
      milestone2 = tmp1

    datediff = self.api('core.utils:format:time')(
        milestone2['time'] - milestone1['time'])

    msg.append(tformat % ('Date', milestone1['dates'],
                          milestone2['dates'], datediff))
    msg.append(tformat % ('Time', milestone1['times'],
                          milestone2['times'], ''))

    msg.append('@g' + '-' * 60)

    for i in FIELDSTOCOMP:
      msg.append(tformat % (i, milestone1[i], milestone2[i],
                            milestone2[i] - milestone1[i]))
    return msg


  def cmd_comp(self, args=None):
    """
    list milestones
    """
    msg = []

    if args['milestone1'] and args['milestone2']:
      milestone1 = self.statdb.getmilestone(args['milestone1'])
      milestone2 = self.statdb.getmilestone(args['milestone2'])
    elif args['milestone1']:
      milestone1 = self.statdb.getmilestone(args['milestone1'])
      milestone2 = self.statdb.getmilestone('current')
    else:
      milestone1 = self.statdb.getmilestone('start')
      milestone2 = self.statdb.getmilestone('current')

    if not milestone1:
      msg.append('milestone %s does not exist' % args['milestone1'])
    if not milestone2:
      msg.append('milestone %s does not exist' % args['milestone2'])

    if not milestone2 or not milestone1:
      return True, msg

    msg = self.formatcomp(milestone1, milestone2)

    return True, msg

  @staticmethod
  def _format_row(rowname, data1, data2, datacolor="@W",
                  headercolor="@C"):
    """
    format a row of data
    """
    lstr = '%s%-14s : %s%-12s %s%-12s' % (headercolor, rowname,
                                          datacolor, data1,
                                          datacolor, data2)

    return lstr

  def show_quest(self, args):
    """
    show info for a specific quest in the database
    """
    msg = []

    tid = args['number']

    questinfo = self.api('%s:get:single:row' % (self.database_name))(tid, 'quests')

    if questinfo:
      questinfo = questinfo[0]

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    msg.append("@G%-6s %-2s %-2s %-2s %-2s %-3s" \
                " %-2s %-2s %-2s %-2s %-4s %-3s   %s" % \
                   ("ID", "QP", "MC", "TR", "LK",
                    "DBL", "TL", "TP", "TN",
                    "PR", "Gold", "Lvl", "Time"))
    msg.append(div)

    dbl = ''
    if int(questinfo['double']) == 1:
      dbl = dbl + 'D'
    if int(questinfo['daily']) == 1:
      dbl = dbl + 'E'

    leveld = self.api('aardwolf.aardu:convertlevel')(questinfo['level'])

    ttime = self.api('core.utils:format:time')(questinfo['finishtime'] - \
                                              questinfo['starttime'])
    if int(questinfo['failed']) == 1:
      ttime = 'Failed'
    msg.append("%-6s %2s %2s %2s %2s %3s" \
                  " %2s %2s %2s %2s %4s %3s %8s" % \
                    (questinfo['quest_id'], questinfo['qp'],
                     questinfo['mccp'], questinfo['tierqp'], questinfo['lucky'],
                     dbl, questinfo['totqp'], questinfo['tp'],
                     questinfo['trains'], questinfo['pracs'], questinfo['gold'],
                     leveld['level'], ttime))

    msg.append(div)

    msg.append('%-25s %-25s %-20s' % (questinfo['mobname'],
                                      questinfo['mobroom'],
                                      questinfo['mobarea']))

    msg.append(div)

    return True, msg

  def cmd_quests(self, args=None): # pylint: disable=too-many-statements
    """
    show quest stats
    """
    if self.statdb.getlastrowid('stats') <= 0:
      return True, ['No stats available']

    if self.statdb.getlastrowid('quests') <= 0:
      return True, ['No quests stats are available']

    count = 0

    if args:
      if args['number']:
        return self.show_quest(args)
      else:
        count = args['count']

    msg = []

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    tqrow = self.statdb.select(
        """SELECT AVG(finishtime - starttime) as avetime,
                      SUM(qp) as qp,
                      AVG(qp) as qpquestave,
                      AVG(tierqp) as tierqpave,
                      SUM(tierqp) as tierqp,
                      AVG(mccp) as mccpave,
                      SUM(mccp) as mccp,
                      AVG(lucky) as luckyave,
                      SUM(lucky) as lucky,
                      AVG(opk) as opkave,
                      SUM(opk) as opk,
                      AVG(hardcore) as hardcoreave,
                      SUM(hardcore) as hardcore,
                      SUM(tp) as tp,
                      AVG(tp) as tpave,
                      SUM(trains) as trains,
                      AVG(trains) as trainsave,
                      SUM(pracs) as pracs,
                      AVG(pracs) as pracsave,
                      COUNT(*) as qindb,
                      SUM(totqp) as dboverall,
                      AVG(totqp) as dboverallave,
                      SUM(gold) as gold,
                      AVG(gold) as avegold FROM quests where failed = 0""")
    stats = tqrow[0]
    tfrow = self.statdb.select(
        "SELECT COUNT(*) as failedindb FROM quests where failed != 0")
    stats.update(tfrow[0])
    tsrow = self.statdb.select(
        """SELECT qpearned, questscomplete, questsfailed,
            totallevels FROM stats WHERE milestone = 'current'""")
    stats.update(tsrow[0])
    stats['indb'] = stats['failedindb'] + stats['qindb']
    stats['qplevelave'] = stats['qpearned']/float(stats['totallevels'])
    msg.append(self._format_row('DB Stats', 'Total', 'In DB', '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("Quests",
                                stats['questscomplete'] + stats['questsfailed'],
                                stats['indb']))
    msg.append(self._format_row("Quests Comp",
                                stats['questscomplete'], stats['qindb']))
    msg.append(self._format_row("Quests Failed",
                                stats['questsfailed'], stats['failedindb']))
    msg.append('')
    msg.append(self._format_row("QP Stats", "Total", "Average", '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("Overall QP", stats['qpearned'],
                                format_float(stats['qplevelave'], "/level")))
    msg.append(self._format_row("Quest QP", stats['qp'],
                                format_float(stats['qpquestave'], "/quest")))
    msg.append(self._format_row("MCCP", stats['mccp'],
                                format_float(stats['mccpave'], "/quest")))
    msg.append(self._format_row("Lucky", stats['lucky'],
                                format_float(stats['luckyave'], "/quest")))
    msg.append(self._format_row("Tier", stats['tierqp'],
                                format_float(stats['tierqpave'], "/quest")))
    msg.append(self._format_row("OPK", stats['opk'],
                                format_float(stats['opkave'], "/quest")))
    msg.append(self._format_row("Hardcore", stats['hardcore'],
                                format_float(stats['hardcoreave'], "/quest")))
    msg.append(self._format_row("QP Per Quest", "",
                                format_float(stats['dboverallave'], "/quest")))
    msg.append(self._format_row("Gold",
                                self.api('core.utils:convert:to:readable:number')(stats['gold'], 2),
                                "%d/quest" % stats['avegold']))
    msg.append(self._format_row("Time", "",
                                self.api('core.utils:format:time')(stats['avetime'])))
    msg.append('')
    msg.append(self._format_row("Bonus Rewards", "Total",
                                "Average", '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("TP", stats['tp'],
                                format_float(stats['tpave'], "/quest")))
    msg.append(self._format_row("Trains", stats['trains'],
                                format_float(stats['trainsave'], "/quest")))
    msg.append(self._format_row("Pracs", stats['pracs'],
                                format_float(stats['pracsave'], "/quest")))

    if int(count) > 0:
      lastitems = self.statdb.getlast('quests', int(count))
      if len(lastitems) > 0: # pylint: disable=len-as-condition
        msg.append('')
        msg.append("@G%-6s %-2s %-2s %-2s %-2s %-2s %-2s %-3s" \
                      " %-2s %-2s %-2s %-2s %-4s %-3s   %s" % \
                        ("ID", "QP", "MC", "TR", "LK",
                         "PK", "HC", "DBL", "TL", "TP", "TN",
                         "PR", "Gold", "Lvl", "Time"))
        msg.append(div)

        for item in lastitems:
          dbl = ''
          if int(item['double']) == 1:
            dbl = dbl + 'D'
          if int(item['daily']) == 1:
            dbl = dbl + 'E'

          leveld = self.api('aardwolf.aardu:convertlevel')(item['level'])

          ttime = self.api('core.utils:format:time')(item['finishtime'] - \
                                                    item['starttime'])
          if int(item['failed']) == 1:
            ttime = 'Failed'
          msg.append("%-6s %2s %2s %2s %2s %2s %2s %3s" \
                        " %2s %2s %2s %2s %4s %3s %8s" % \
                         (item['quest_id'], item['qp'],
                          item['mccp'], item['tierqp'], item['lucky'], item['opk'],
                          item['hardcore'], dbl, item['totqp'], item['tp'],
                          item['trains'], item['pracs'], item['gold'],
                          leveld['level'], ttime))

    return True, msg

  def show_level(self, args): # pylint: disable=too-many-locals,too-many-statements,too-many-branches
    """
    show info for a specific level in the database
    """
    msg = []

    tid = args['number']

    levelinfo = self.api('%s:get:single:row' % (self.database_name))(tid, 'levels')

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    if levelinfo:
      levelinfo = levelinfo[0]

    bonus = 0
    if int(levelinfo['bonustrains']) > 0:
      bonus = bonus + int(levelinfo['bonustrains'])
    if int(levelinfo['blessingtrains']) > 0:
      bonus = bonus + int(levelinfo['blessingtrains'])
    if int(levelinfo['battlelearntrains'] > 0):
      bonus = bonus + int(levelinfo['battlelearntrains'])

    leveld = self.api('aardwolf.aardu:convertlevel')(levelinfo['level'])
    levels = 're%st%sr%sl%s' % (leveld['redos'], leveld['tier'],
                                leveld['remort'], leveld['level'])

    if levelinfo['finishtime'] != '-1' and levelinfo['starttime'] != '-1':
      ttime = self.api('core.utils:format:time')(levelinfo['finishtime'] - \
                                                levelinfo['starttime'])
    else:
      ttime = ''

    if levelinfo['type'] == 'level':
      ltype = 'lev'
    else:
      ltype = 'pup'

    msg.append("@G%-6s %-5s %-7s %-s" % ("ID", "Type", "TotLvl", "Actual"))
    msg.append("%-6s %-5s %-7s %-s" % (levelinfo['level_id'], ltype, levelinfo['level'],
                                       levels))

    msg.append("@G%-6s %2s %2s %-2s %-2s " % ("", "HP", "MN", "MV", "PR"))
    msg.append("%-6s %2s %2s %-2s %-2s" % ("", levelinfo['hp'], levelinfo['mp'],
                                           levelinfo['mv'], levelinfo['pracs']))

    msg.append("@G%-6s %-2s %-2s %-2s %-2s" % ("", "TR", "BO", "BL", "BT"))
    msg.append("%-6s %-2s %-2s %-2s %-2s" % ("", levelinfo['trains'],
                                             levelinfo['bonustrains'],
                                             levelinfo['blessingtrains'],
                                             levelinfo['battlelearntrains']))

    msg.append("@G%-6s %-1s %-1s %-1s %-1s %-1s %-1s" % \
                ("", "S", "I", "W", "C", "D", "L"))
    msg.append("%-6s %-1s %-1s %-1s %-1s %-1s %-1s" % \
                ("", levelinfo['str'], levelinfo['int'],
                 levelinfo['wis'], levelinfo['con'], levelinfo['dex'],
                 levelinfo['luc']))

    stmt = "SELECT count(*) as count, AVG(totalxp) as average FROM " \
             "mobkills where time > %d and time < %d and xp > 0" % \
              (levelinfo['starttime'], levelinfo['finishtime'])
    tst = self.api('%s:select' % (self.database_name))(stmt)
    count = tst[0]['count']
    ave = tst[0]['average']

    if levelinfo['starttime'] or levelinfo['finishtime']:
      msg.append(div)

      if levelinfo['starttime']:
        msg.append('Started  : %s' % time.strftime(
            "%a, %d %b %Y %H:%M:%S +0000",
            time.localtime(levelinfo['starttime'])))

      if levelinfo['finishtime']:
        if levelinfo['finishtime'] == -1:
          fstr = 'Current'
        else:
          fstr = time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                               time.localtime(levelinfo['finishtime']))
        msg.append('Finished : %s' % fstr)

    if count > 0 and ave > 0:
      msg.append(div)
      length = levelinfo['finishtime'] - levelinfo['starttime']
      if ttime:
        tmsg = "It took %s with " % ttime
      else:
        tmsg = ""
      tmsg = tmsg + '@G%s@w mobs killed' % count
      tmsg = tmsg + ' (@G%02.02f@w xp/mob)' % (ave)
      perlevel = self.api('net.GMCP:value:get')('char.base.perlevel')
      if length and perlevel:
        expmin = self.api('net.GMCP:value:get')('char.base.perlevel')/(length/60)
        tmsg = tmsg + ' @G%02d@w xp/min' % (expmin)

      msg.append(tmsg)
      msg.append(div)

    return True, msg

  def cmd_levels(self, args=None): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    show level stats
    """
    if self.statdb.getlastrowid('stats') <= 0:
      return True, ['No stats available']

    if self.statdb.getlastrowid('levels') <= 0:
      return True, ['No levels/pups stats available']

    count = 0

    if args:
      if args['number']:
        return self.show_level(args)
      else:
        count = args['count']

    msg = []
    pups = {}
    levels = {}

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    lrow = self.statdb.select(
        "SELECT totallevels, qpearned FROM stats WHERE milestone = 'current'")
    levels.update(lrow[0])

    prow = self.statdb.select(
        "SELECT MAX(powerupsall) as powerupsall FROM stats")
    pups.update(prow[0])

    levels['qpave'] = int(levels['qpearned']) / int(levels['totallevels'])

    llrow = self.statdb.select("""
             SELECT AVG(trains) as avetrains,
                    AVG(bonustrains) as avebonustrains,
                    AVG(blessingtrains) as aveblessingtrains,
                    AVG(battlelearntrains) as avebattlelearntrains,
                    SUM(trains + bonustrains + blessingtrains + battlelearntrains) as totaltrains,
                    SUM(pracs) as totalpracs,
                    COUNT(*) as indb
                    FROM levels where type = 'level' and trains > 0
                    """)
    levels.update(llrow[0])

    ltrow = self.statdb.select("""
             SELECT AVG(finishtime - starttime) as avetime FROM levels
             where type = 'level' and finishtime <> -1 and trains > 0
                    """)
    levels.update(ltrow[0])

    pprow = self.statdb.select("""
             SELECT AVG(trains) as avetrains,
                    AVG(bonustrains) as avebonustrains,
                    AVG(blessingtrains) as aveblessingtrains,
                    AVG(battlelearntrains) as avebattlelearntrains,
                    SUM(trains + bonustrains + blessingtrains + battlelearntrains) as totaltrains,
                    COUNT(*) as indb
                    FROM levels where type = 'pup'
                    """)
    pups.update(pprow[0])

    ptrow = self.statdb.select("""
             SELECT AVG(finishtime - starttime) as avetime FROM levels
             where type = 'pup' and finishtime <> -1
                    """)
    pups.update(ptrow[0])

    msg.append(self._format_row('Type', 'Levels', 'Pups', '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("Total Overall",
                                levels['totallevels'], pups['powerupsall']))
    msg.append(self._format_row("Total In DB",
                                levels['indb'], pups['indb']))
    msg.append(self._format_row("Total Trains",
                                levels['totaltrains'] or 0, pups['totaltrains'] or 0))

    trainitems = [
        ['Ave Trains', 'avetrains'],
        ['Ave Bon Trains', 'avebonustrains'],
        ['Ave Bls Trains', 'aveblessingtrains'],
        ['Ave BaL Trains', 'avebattlelearntrains'],
    ]

    levelave = float(0)
    pupave = float(0)
    for i in trainitems:
      title = i[0]
      lkey = i[1]
      lave = format_float(levels[lkey])
      pave = format_float(pups[lkey])
      levelave = float(levelave) + float(lave)
      pupave = float(pupave) + float(pave)
      msg.append(self._format_row(title,
                                  lave or 0, pave or 0))

    msg.append(self._format_row("Ave Overall",
                                levelave or 0, pupave or 0))
    msg.append(self._format_row("Total Pracs",
                                levels['totalpracs'], ""))

    if levels['avetime']:
      lavetime = self.api('core.utils:format:time')(levels['avetime'])
    else:
      lavetime = ""

    if pups['avetime']:
      pavetime = self.api('core.utils:format:time')(pups['avetime'])
    else:
      pavetime = ""

    msg.append(self._format_row("Time", lavetime, pavetime))

    if int(count) > 0:
      lastitems = self.statdb.getlast('levels', int(count))

      if len(lastitems) > 0: # pylint: disable=len-as-condition
        msg.append('')
        msg.append("@G%-6s %-3s %2s %2s %2s %-2s %-2s %-2s" \
                     " %-2s %-1s %-1s %-1s %-1s %-1s %-1s   %s" % \
                       ("ID", "Lvl", "T",
                        "TR", "BT", "PR", "HP", "MN", "MV", "S",
                        "I", "W", "C", "D", "L", "Time"))
        msg.append(div)

        for item in lastitems:
          bonus = 0
          if int(item['bonustrains']) > 0:
            bonus = bonus + int(item['bonustrains'])
          if int(item['blessingtrains']) > 0:
            bonus = bonus + int(item['blessingtrains'])

          leveld = self.api('aardwolf.aardu:convertlevel')(item['level'])

          if item['finishtime'] != '-1' and item['starttime'] != '-1':
            ttime = self.api('core.utils:format:time')(item['finishtime'] - \
                                                      item['starttime'])
          else:
            ttime = ''

          if item['type'] == 'level':
            ltype = 'L'
          else:
            ltype = 'P'

          msg.append("%-6s %-3s %2s %2s %2s %-2s %-2s %-2s" \
                     " %-2s %-1s %-1s %-1s %-1s %-1s %-1s   %s" % \
                       (item['level_id'], leveld['level'], ltype, item['trains'],
                        bonus, item['pracs'], item['hp'], item['mp'],
                        item['mv'], item['str'], item['int'], item['wis'],
                        item['con'], item['dex'], item['luc'], ttime))

    return True, msg

  def show_cp(self, args):
    """
    show info for a specific cp in the database
    """
    msg = []

    tid = args['number']

    cpinfo = self.api('%s:get:single:row' % (self.database_name))(tid, 'campaigns')

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    if cpinfo:
      cpinfo = cpinfo[0]

    mobs = self.api('%s:select' % (self.database_name))(
        "SELECT * FROM cpmobs WHERE cp_id = %s" % tid)

    msg.append("@G%-6s %-12s %-2s %-2s %-2s %-2s %-2s %6s %-4s  %s" % \
                  ("ID", "Lvl", "QP", "BN",
                   "TP", "TN", "PR", "Gold", "Mobs", "Time"))
    msg.append(div)

    leveld = self.api('aardwolf.aardu:convertlevel')(cpinfo['level'])
    levelstr = 'T%d R%d L%d' % (leveld['tier'], leveld['remort'],
                                leveld['level'])

    if cpinfo['finishtime'] != '-1' and cpinfo['starttime'] != '-1':
      ttime = self.api('core.utils:format:time')(cpinfo['finishtime'] - \
                                                cpinfo['starttime'])
    else:
      ttime = ''

    if int(cpinfo['failed']) == 1:
      ttime = 'Failed'

    msg.append("%-6s %-12s %-2s %2s %2s %2s %2s %6s  %-3s  %s" % \
                  (cpinfo['cp_id'], levelstr, cpinfo['qp'], cpinfo['bonusqp'],
                   cpinfo['tp'], cpinfo['trains'], cpinfo['pracs'], cpinfo['gold'],
                   len(mobs), ttime))

    msg.append(div)
    msg.append("@G%-30s %-30s" % ("Name", "Location"))
    msg.append(div)

    for i in mobs:
      msg.append("@G%-30s %-30s" % (i['name'],
                                    i['location']))

    msg.append(div)

    return True, msg

  def cmd_cps(self, args=None): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    show cp stats
    """
    if self.statdb.getlastrowid('stats') <= 0:
      return True, ['No stats available']

    if self.statdb.getlastrowid('campaigns') <= 0:
      return True, ['No campaign stats available']

    count = 0

    if args:
      if args['number']:
        return self.show_cp(args)
      else:
        count = args['count']

    msg = []
    stats = {}

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    trow = self.statdb.select(
        "SELECT campaignsdone, campaignsfld, totallevels " \
        "FROM stats WHERE milestone = 'current'")
    stats.update(trow[0])

    trow = self.statdb.select(
        """SELECT AVG(finishtime - starttime) as avetime,
                  SUM(qp) as totalqp,
                  AVG(qp) as aveqp,
                  SUM(tp) as totaltp,
                  AVG(tp) as avetp,
                  SUM(trains) as totaltrains,
                  AVG(trains) as avetrains,
                  SUM(pracs) as totalpracs,
                  AVG(pracs) as avepracs,
                  COUNT(*) as cindb,
                  SUM(gold) as totalgold,
                  AVG(gold) as avegold
                  FROM campaigns where failed = 0""")
    stats.update(trow[0])

    trow = self.statdb.select(
        "SELECT COUNT(*) as failedindb FROM campaigns where failed != 0")
    stats.update(trow[0])

    stats['indb'] = int(stats['cindb']) + int(stats['failedindb'])
    stats['totalcps'] = int(stats['campaignsdone']) + \
                        int(stats['campaignsfld'])

    msg.append(self._format_row('DB Stats', 'Total', 'In DB', '@G', '@G'))
    msg.append(div)

    msg.append(self._format_row("Overall",
                                stats['totalcps'], stats['indb'] or 0))
    msg.append(self._format_row("Completed",
                                stats['campaignsdone'], stats['cindb'] or 0))
    msg.append(self._format_row("Failed",
                                stats['campaignsfld'], stats['failedindb'] or 0))

    msg.append('')
    msg.append(self._format_row('CP Stats', 'Total', 'Average', '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("QP",
                                stats['totalqp'] or 0,
                                format_float(stats['aveqp'], "/CP")))
    if stats['totalgold']:
      tempg = self.api('core.utils:convert:to:readable:number')(stats['totalgold'])
    else:
      tempg = 0

    msg.append(self._format_row("Gold",
                                tempg,
                                "%d/CP" % stats['avegold']))
    if stats['avetime']:
      atime = self.api('core.utils:format:time')(stats['avetime'])
    else:
      atime = ""

    msg.append(self._format_row("Time", "", atime))

    msg.append('')
    msg.append(self._format_row("Bonus Rewards", "Total",
                                "Average", '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("TP",
                                stats['totaltp'] or 0,
                                format_float(stats['avetp'], "/CP")))
    msg.append(self._format_row("Trains",
                                stats['totaltrains'] or 0,
                                format_float(stats['avetrains'], "/CP")))

    msg.append(self._format_row("Pracs",
                                stats['totalpracs'] or 0,
                                format_float(stats['avepracs'], "/CP")))

    if int(count) > 0:
      lastitems = self.statdb.getlast('campaigns', int(count))

      mobc = self.statdb.selectbykeyword(
          'SELECT cp_id, count(*) as mobcount from cpmobs group by cp_id',
          'cp_id')

      if len(lastitems) > 0: # pylint: disable=len-as-condition
        msg.append('')
        msg.append("@G%-6s %-12s %-2s %-2s %-2s %-2s %-2s %6s %-4s  %s" % \
                    ("ID", "Lvl", "QP", "BN", "TP", "TN",
                     "PR", "Gold", "Mobs", "Time"))
        msg.append(div)

        for item in lastitems:
          leveld = self.api('aardwolf.aardu:convertlevel')(item['level'])
          levelstr = 'T%d R%d L%d' % (leveld['tier'], leveld['remort'],
                                      leveld['level'])

          if item['finishtime'] != '-1' and item['starttime'] != '-1':
            ttime = self.api('core.utils:format:time')(item['finishtime'] - \
                                                      item['starttime'])
          else:
            ttime = ''

          if int(item['failed']) == 1:
            ttime = 'Failed'

          msg.append("%-6s %-12s %-2s %2s %2s %2s %2s %6s  %-3s  %s" % \
                      (item['cp_id'], levelstr, item['qp'], item['bonusqp'],
                       item['tp'], item['trains'], item['pracs'], item['gold'],
                       mobc[item['cp_id']]['mobcount'], ttime))

    return True, msg

  def show_gq(self, args):
    """
    show info for a specific gq in the database
    """
    msg = []

    tid = args['number']

    gqinfo = self.api('%s:get:single:row' % (self.database_name))(tid, 'gquests')

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    if gqinfo:
      gqinfo = gqinfo[0]

    mobs = self.api('%s:select' % (self.database_name))(
        "SELECT SUM(num) FROM gqmobs WHERE gq_id = %s" % tid)


    msg.append("@G%-6s %-12s %-2s %-2s %-2s %-2s %-2s %6s %-4s  %s" % \
                ("ID", "Lvl", "QP", "QM", "TP",
                 "TN", "PR", "Gold", "Mobs", "Time"))
    msg.append(div)


    leveld = self.api('aardwolf.aardu:convertlevel')(gqinfo['level'])
    levelstr = 'T%d R%d L%d' % (leveld['tier'], leveld['remort'],
                                leveld['level'])

    if gqinfo['finishtime'] != '-1' and gqinfo['starttime'] != '-1':
      ttime = self.api('core.utils:format:time')(gqinfo['finishtime'] - \
                                                gqinfo['starttime'])
    else:
      ttime = ''

    msg.append("%-6s %-12s %2s %2s %2s %2s %2s %6s  %-3s  %s" % \
                (gqinfo['gq_id'], levelstr, gqinfo['qp'], gqinfo['qpmobs'],
                 gqinfo['tp'], gqinfo['trains'], gqinfo['pracs'],
                 gqinfo['gold'], len(mobs), ttime))

    msg.append(div)
    msg.append("@G%-5s %-30s %-30s" % ("Num", "Name", "Location"))
    msg.append(div)

    for i in mobs:
      msg.append("@G%-5s %-30s %-30s" % (i['num'], i['name'],
                                         i['location']))

    msg.append(div)

    return True, msg

  def cmd_gqs(self, args=None): # pylint: disable=too-many-locals,too-many-statements
    """
    show gq stats
    """
    if self.statdb.getlastrowid('stats') <= 0:
      return True, ['No stats available']

    if self.statdb.getlastrowid('gquests') <= 0:
      return True, ['No gq stats available']

    count = 0

    if args:
      if args['number']:
        return self.show_gq(args)
      else:
        count = args['count']

    msg = []
    stats = {}

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    wrow = self.statdb.select(
        """SELECT AVG(finishtime - starttime) as avetime,
                  SUM(qp) as qp,
                  AVG(qp) as qpave,
                  SUM(qpmobs) as qpmobs,
                  AVG(qpmobs) as qpmobsave,
                  SUM(tp) as tp,
                  AVG(tp) as tpave,
                  SUM(trains) as trains,
                  AVG(trains) as trainsave,
                  SUM(pracs) as pracs,
                  AVG(pracs) as pracsave,
                  COUNT(*) as indb,
                  SUM(gold) as gold,
                  AVG(gold) as avegold
                  FROM gquests where won = 1""")
    stats['won'] = wrow[0]

    trow = self.statdb.select(
        "SELECT gquestswon FROM stats WHERE milestone = 'current'")
    stats.update(trow[0])

    trow = self.statdb.select(
        """SELECT AVG(finishtime - starttime) as avetime,
                 SUM(qpmobs) as totalqp,
                 AVG(qpmobs) as aveqp,
                 COUNT(*) as indb
                 FROM gquests where won != 1""")
    stats['lost'] = trow[0]

    trow = self.statdb.select(
        """SELECT SUM(qpmobs + qp) as overallqp,
                 AVG(qpmobs + qp) as aveoverallqp
                 FROM gquests""")
    stats.update(trow[0])

    stats['indb'] = stats['won']['indb'] + stats['lost']['indb']
    stats['overall'] = stats['gquestswon'] + stats['lost']['indb']

    msg.append(self._format_row('GQ Stats', 'Total', 'In DB', '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("Won",
                                stats['gquestswon'], stats['won']['indb'] or 0))
    msg.append(self._format_row("Lost",
                                "", stats['lost']['indb'] or 0))
    msg.append(self._format_row("Overall",
                                stats['overall'], stats['indb'] or 0))
    msg.append(self._format_row("QP",
                                stats['overallqp'],
                                format_float(stats['aveoverallqp'], "/GQ")))

    msg.append('')
    msg.append(self._format_row('GQ Won Stats', 'Total', 'Average',
                                '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("GQ QP",
                                stats['won']['qp'],
                                format_float(stats['won']['qpave'], "/GQ")))
    msg.append(self._format_row("GQ MOB QP",
                                stats['won']['qpmobs'],
                                format_float(stats['won']['qpmobsave'], "/GQ")))

    if stats['won']['avetime']:
      atime = self.api('core.utils:format:time')(stats['won']['avetime'])
    else:
      atime = ""

    msg.append(self._format_row("Time", "", atime))
    msg.append(self._format_row("Gold",
                                self.api('core.utils:convert:to:readable:number')(stats['won']['gold']),
                                "%d/GQ" % stats['won']['avegold']))
    msg.append(self._format_row("TP",
                                stats['won']['tp'],
                                format_float(stats['won']['tpave'], "/GQ")))
    msg.append(self._format_row("Trains",
                                stats['won']['trains'],
                                format_float(stats['won']['trainsave'], "/GQ")))
    msg.append(self._format_row("Pracs",
                                stats['won']['pracs'],
                                format_float(stats['won']['pracsave'], "/GQ")))

    msg.append('')
    msg.append(self._format_row('GQ Lost Stats', 'Total', 'Average',
                                '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("GQ MOB QP",
                                stats['lost']['totalqp'],
                                format_float(stats['lost']['aveqp'], "/GQ")))

    if int(count) > 0:
      lastitems = self.statdb.getlast('gquests', int(count))

      mobc = self.statdb.selectbykeyword(
          'SELECT gq_id, SUM(num) as mobcount from gqmobs group by gq_id',
          'gq_id')

      if len(lastitems) > 0: # pylint: disable=len-as-condition
        msg.append('')
        msg.append("@G%-6s %-12s %-2s %-2s %-2s %-2s %-2s %6s %-4s  %s" % \
                    ("ID", "Lvl", "QP", "QM", "TP",
                     "TN", "PR", "Gold", "Mobs", "Time"))
        msg.append(div)

        for item in lastitems:
          leveld = self.api('aardwolf.aardu:convertlevel')(item['level'])
          levelstr = 'T%d R%d L%d' % (leveld['tier'], leveld['remort'],
                                      leveld['level'])

          if item['finishtime'] != '-1' and item['starttime'] != '-1':
            ttime = self.api('core.utils:format:time')(item['finishtime'] - \
                                                      item['starttime'])
          else:
            ttime = ''

          msg.append("%-6s %-12s %2s %2s %2s %2s %2s %6s  %-3s  %s" % \
                      (item['gq_id'], levelstr, item['qp'], item['qpmobs'],
                       item['tp'], item['trains'], item['pracs'], item['gold'],
                       mobc[item['gq_id']]['mobcount'], ttime))

    return True, msg

  def cmd_mobs(self, args=None): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    show mobs stats
    """
    if self.statdb.getlastrowid('stats') <= 0:
      return True, ['No stats available']

    if self.statdb.getlastrowid('mobkills') <= 0:
      return True, ['No mob stats available']

    count = 0
    if args:
      count = args['count']

    msg = []
    stats = {}

    linelen = self.api('net.proxy:setting:get')('linelen')
    div = '@B' + '-' * linelen

    trow = self.statdb.select(
        "SELECT monsterskilled FROM stats WHERE milestone = 'current'")
    stats.update(trow[0])

    trow = self.statdb.select(
        """SELECT SUM(xp) AS xp,
                  SUM(rarexp) as rarexp,
                  SUM(bonusxp) AS bonusxp,
                  SUM(blessingxp) AS blessingxp,
                  SUM(totalxp) as totalxp,
                  AVG(xp) AS avexp,
                  AVG(totalxp) AS avetotalxp,
                  SUM(tp) AS tp,
                  SUM(vorpal) AS vorpal,
                  SUM(assassinate) AS assassinate,
                  SUM(disintegrate) AS disintegrate,
                  SUM(banishment) AS banishment,
                  SUM(slit) AS slit,
                  SUM(deathblow) AS deathblow,
                  SUM(gold) AS gold,
                  AVG(gold) AS avegold,
                  COUNT(*) AS indb
                  FROM mobkills""")
    stats.update(trow[0])

    trow = self.statdb.select(
        """SELECT AVG(bonusxp) as avebonusxp,
                 COUNT(*) as bonusmobsindb
                 FROM mobkills where bonusxp > 0""")
    stats.update(trow[0])

    trow = self.statdb.select(
        """SELECT AVG(blessingxp) as aveblessxp,
                 COUNT(*) as blessmobsindb
                 FROM mobkills where blessingxp > 0""")
    stats.update(trow[0])

    trow = self.statdb.select(
        """SELECT AVG(rarexp) as averarexp,
                 COUNT(*) as raremobsindb
                 FROM mobkills where rarexp > 0""")
    stats.update(trow[0])

    msg.append(self._format_row('DB Stats', 'Total', 'In DB', '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("Overall",
                                stats['monsterskilled'], stats['indb'] or 0))
    msg.append(self._format_row("Rare Mobs",
                                "", stats['raremobsindb'] or 0))
    msg.append(self._format_row("Bonus Mobs",
                                "", stats['bonusmobsindb'] or 0))
    msg.append(self._format_row("Blessing Mobs",
                                "", stats['blessmobsindb'] or 0))

    msg.append('')
    msg.append(self._format_row('Stats', 'Total', 'Average', '@G', '@G'))
    msg.append(div)
    msg.append(self._format_row("XP",
                                stats['xp'],
                                format_float(stats['avexp'], "/kill")))
    msg.append(self._format_row("Rare XP",
                                stats['rarexp'],
                                format_float(stats['averarexp'], "/kill")))
    msg.append(self._format_row("Double XP",
                                stats['bonusxp'],
                                format_float(stats['avebonusxp'], "/kill")))
    msg.append(self._format_row("Blessing XP",
                                stats['blessingxp'],
                                format_float(stats['aveblessxp'], "/kill")))
    msg.append(self._format_row("Total XP",
                                stats['totalxp'],
                                format_float(stats['avetotalxp'], "/kill")))
    msg.append(self._format_row("Gold",
                                self.api('core.utils:convert:to:readable:number')(stats['gold']),
                                "%d/kill" % stats['avegold']))
    msg.append(self._format_row("TP",
                                stats['tp'],
                                format_float(stats['tp'] / float(stats['indb']),
                                             "/kill")))

    avetype = stats['vorpal'] / float(stats['indb'])
    msg.append(self._format_row("Vorpal",
                                stats['vorpal'],
                                format_float(avetype, "/kill") or ""))
    avetype = stats['assassinate'] / float(stats['indb'])
    msg.append(self._format_row("Assassinate",
                                stats['assassinate'],
                                format_float(avetype, "/kill") or ""))
    avetype = stats['slit'] / float(stats['indb'])
    msg.append(self._format_row("Slit",
                                stats['slit'],
                                format_float(avetype, "/kill") or ""))
    avetype = stats['banishment'] / float(stats['indb'])
    msg.append(self._format_row("Banishment",
                                stats['banishment'],
                                format_float(avetype, "/kill") or ""))
    avetype = stats['deathblow'] / float(stats['indb'])
    msg.append(self._format_row("Deathblow",
                                stats['deathblow'],
                                format_float(avetype, "/kill") or ""))
    avetype = stats['disintegrate'] / float(stats['indb'])
    msg.append(self._format_row("Disintegrate",
                                stats['disintegrate'],
                                format_float(avetype, "/kill") or ""))

    if int(count) > 0:
      lastitems = self.statdb.getlast('mobkills', int(count))

      if lastitems:
        msg.append('')
        msg.append("@G%3s %-18s %-3s %-3s %-3s %-3s %2s %1s %s" % \
                      ("Lvl", "Mob", "TXP", "XP", "RXP",
                       "OXP", "TP", "S", "Gold"))
        msg.append(div)

        for item in lastitems:
          leveld = self.api('aardwolf.aardu:convertlevel')(item['level'])
          levelstr = leveld['level']

          bonus = ''
          if int(item['bonusxp']) != 0:
            bonus = bonus + "D"
          if int(item['blessingxp']) != 0:
            bonus = bonus + "E"

          spec = ''
          if int(item['banishment']) == 1:
            spec = 'B'
          elif int(item['vorpal']) == 1:
            spec = 'V'
          elif int(item['assassinate']) == 1:
            spec = 'A'
          elif int(item['slit']) == 1:
            spec = 'S'
          elif int(item['deathblow']) == 1:
            spec = 'D'
          elif int(item['disintegrate']) == 1:
            spec = 'I'

          mtp = ''
          if int(item['tp']) == 1:
            mtp = '1'

          xpd = item['xp']
          rarexp = item['rarexp']

          tline = "%3s %-18s %-3s %-3s %-3s %-3s %2s %1s %s"

          if item['noexp'] == 1:
            tline = "%3s %-18s @R%-3s %-3s %-3s %-3s@w %2s %1s %s"


          msg.append(tline % (levelstr, item['name'][0:18], item['totalxp'],
                              xpd, rarexp, bonus,
                              mtp, spec, item['gold']))
    return True, msg

  def questevent(self, args):
    """
    handle a quest completion
    """
    self.statdb.savequest(args)

  def whoisevent(self, args):
    """
    handle whois data
    """
    self.statdb.savewhois(args)

  def cpevent(self, args):
    """
    handle a cp
    """
    self.statdb.savecp(args)

  def gqevent(self, args):
    """
    handle a gq
    """
    self.statdb.savegq(args)

  def levelevent(self, args):
    """
    handle a level
    """
    levelinfo = copy.deepcopy(args)
    self.statdb.savelevel(levelinfo)

  def mobkillevent(self, args):
    """
    handle a mobkill
    """
    self.statdb.savemobkill(args)

  def uninitialize(self, _=None):
    """
    handle uninitializing
    """
    AardwolfBasePlugin.uninitialize(self)
    self.statdb.close()

  def heroevent(self, args):
    """
    add a hero/super milestone
    """
    tlist = self.api('aardwolf.aardu:convertlevel')(
        self.api('aardwolf.aardu:getactuallevel')())
    if int(tlist['tier']) == 9:
      milestone = "t%s+%sr%sl%s" % (tlist['tier'], tlist['redos'],
                                    tlist['remort'], tlist['level'])
    else:
      milestone = "t%sr%sl%s" % (tlist['tier'],
                                 tlist['remort'], tlist['level'])

    if args['eventname'] == 'aard_level_remort':
      if self.statdb:
        self.statdb.setstat('remorts',
                            self.api('net.GMCP:value:get')('char.base.remorts'))
        self.statdb.setstat('tier',
                            self.api('net.GMCP:value:get')('char.base.tier'))
        alev = self.api('aardu.getactuallevel')()
        self.statdb.setstat('totallevels', alev)
        self.statdb.setstat('level', 1)

    if self.statdb:
      self.statdb.addmilestone(milestone)
